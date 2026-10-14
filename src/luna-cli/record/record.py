"""Own a single recording worker; stop only that worker and let MP4 finalization finish."""
from contextlib import contextmanager
from datetime import datetime
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time


ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location("luna_capture", Path(__file__).parents[1] / "screenshot/screenshot.py")
capture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(capture)


def environment():
    values = dict(os.environ)
    for key in ("LD_LIBRARY_PATH", "LD_PRELOAD"):
        values.pop(key, None)
    return values


def runtime():
    path = Path(os.environ.get("XDG_RUNTIME_DIR", f"/tmp/luna-{os.getuid()}")) / "luna-recording"
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    return path


def process_identity(pid):
    try:
        fields = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
        return fields[19] if fields[0] != "Z" else None
    except (OSError, IndexError, ValueError):
        return None


def read_state():
    try:
        value = json.loads((runtime() / "state.json").read_text())
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def status():
    state = read_state()
    pid = state.get("pid")
    if state.get("running") and type(pid) is int and pid > 1 and state.get("identity") and state["identity"] == process_identity(pid):
        return state
    return {"running": False}


def write_state(value):
    descriptor, temporary = tempfile.mkstemp(prefix=".state-", dir=runtime())
    try:
        with os.fdopen(descriptor, "w") as file:
            json.dump(value, file)
            file.write("\n")
        os.replace(temporary, runtime() / "state.json")
    finally:
        Path(temporary).unlink(missing_ok=True)
    # Also wake an existing shell when the state file was created after its file watch.
    try:
        subprocess.run(["qs", "ipc", "-p", str(ROOT / "src/luna-bar"), "call", "bar", "recordingChanged"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=1)
    except (OSError, subprocess.SubprocessError):
        pass


@contextmanager
def locked(name):
    with (runtime() / name).open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise ValueError("A recording operation is already in progress") from error
        yield


def notify(summary, body, recording=None):
    arguments = ["notify-send", "--app-name=Luna Recording", "--icon=media-record"]
    if recording is not None:
        arguments.append(f"--hint=string:x-luna-recording:{recording}")
    try:
        subprocess.run([*arguments, "--", summary, body], env=environment(), timeout=3,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError):
        pass


def ensure_indicator():
    # A recording always has a visible stop control; CLI use also starts the bar if needed.
    result = subprocess.run([str(ROOT / "bin/luna"), "bar", "start"], env=environment(),
                            capture_output=True, text=True, timeout=15)
    if result.returncode:
        raise ValueError(result.stderr.strip() or "Could not start the recording indicator")


def start(mode):
    if mode not in ("region", "screen"):
        raise ValueError("Choose region or screen")
    if not shutil.which("wf-recorder"):
        raise ValueError("Install wf-recorder before recording")
    with locked("control.lock"):
        if status()["running"]:
            raise ValueError("A recording is already running")
        ensure_indicator()
        capture.hide_launcher()
        arguments = capture.capture_arguments(mode)
        if arguments is None:
            return None

        directory = Path(os.environ.get("LUNA_RECORDING_DIR", str(Path.home() / "Videos/Recordings"))).expanduser().resolve()
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        descriptor, filename = tempfile.mkstemp(prefix="Recording_" + datetime.now().strftime("%Y-%m-%d_%H-%M-%S_"), suffix=".mp4", dir=directory)
        os.close(descriptor)
        path = Path(filename)
        write_state({"running": False})
        worker = None
        try:
            with (runtime() / "worker.log").open("w") as log:
                worker = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "_serve", filename, json.dumps(arguments)],
                                          env=environment(), stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                                          start_new_session=True)
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                state = status()
                if state["running"] and state.get("pid") == worker.pid and state.get("phase") == "recording":
                    # Reap in long-lived callers without holding up the short-lived CLI parent.
                    threading.Thread(target=worker.wait, name="luna-recording-reaper", daemon=True).start()
                    return path
                if worker.poll() is not None:
                    raise ValueError(read_state().get("error") or "The recorder could not start")
                time.sleep(0.05)
            raise ValueError("The recorder did not become ready")
        except BaseException:
            # Until readiness is handed back, cancellation still owns the worker and its recorder.
            if worker is not None:
                if worker.poll() is None:
                    worker.terminate()
                try:
                    worker.wait(timeout=20)
                except subprocess.TimeoutExpired:
                    # The worker owns this process group; do not leave its recorder orphaned.
                    try:
                        os.killpg(worker.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    worker.wait()
            if path.exists() and path.stat().st_size == 0:
                path.unlink()
            raise


def stop():
    with locked("control.lock"):
        state = status()
        if not state["running"]:
            return None
        # A pidfd prevents PID reuse between validating our worker and signalling it.
        try:
            descriptor = os.pidfd_open(state["pid"])
        except ProcessLookupError:
            return None
        try:
            if process_identity(state["pid"]) != state["identity"]:
                return None
            signal.pidfd_send_signal(descriptor, signal.SIGINT)
        finally:
            os.close(descriptor)
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            current = status()
            if not current["running"] or current.get("pid") != state["pid"]:
                result = read_state()
                if result.get("error"):
                    raise ValueError(result["error"])
                return Path(state["file"])
            time.sleep(0.1)
        raise ValueError("Recording is still finishing; try stopping again shortly")


def serve(filename, arguments):
    path = Path(filename)
    stopping = False
    child = None

    def request_stop(signum, frame):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)
    with locked("worker.lock"):
        state = {"running": True, "pid": os.getpid(), "identity": process_identity(os.getpid()),
                 "file": str(path), "started": time.time(), "phase": "starting"}
        write_state(state)
        error = ""
        try:
            with (runtime() / "recorder.log").open("w+") as log:
                # Software H.264 is portable across GPUs. Even dimensions satisfy yuv420p.
                command = ["wf-recorder", "-y", "-c", "libx264", "-p", "preset=ultrafast",
                           "-p", "crf=23", "-x", "yuv420p", "-F", "pad=ceil(iw/2)*2:ceil(ih/2)*2",
                           "-r", "30", *arguments, "-f", str(path)]
                child = subprocess.Popen(command, env=environment(), stdin=subprocess.DEVNULL,
                                         stdout=log, stderr=log)
                started = time.monotonic()
                while child.poll() is None:
                    if stopping:
                        state["phase"] = "stopping"
                        write_state(state)
                        child.send_signal(signal.SIGINT)
                        try:
                            child.wait(timeout=10)
                        except subprocess.TimeoutExpired:
                            child.terminate()
                            child.wait(timeout=3)
                            raise ValueError("Recorder did not finalize in time; the file may be incomplete")
                        break
                    if state["phase"] == "starting" and time.monotonic() - started > 0.35:
                        state["phase"] = "recording"
                        write_state(state)
                    time.sleep(0.05)
                if child.returncode not in (0, -signal.SIGINT):
                    log.seek(0)
                    detail = log.read()[-3000:].strip()
                    raise ValueError(detail.splitlines()[-1] if detail else "Recorder exited unexpectedly")
                if not path.exists() or path.stat().st_size < 32:
                    raise ValueError("The recording contains no video")
        except (OSError, ValueError, subprocess.SubprocessError) as failure:
            error = str(failure)
        finally:
            if child and child.poll() is None:
                child.kill()
                child.wait()
            if path.exists() and path.stat().st_size == 0:
                path.unlink()
    # Idle means a new worker can acquire the lock immediately, even if feedback is slow.
    write_state({"running": False, "file": str(path), "error": error})
    if error:
        notify("Recording failed", error)
    else:
        notify("Recording saved", path.name, recording=path)


def main():
    action = sys.argv[1] if len(sys.argv) > 1 else "region"
    if action == "_serve":
        serve(sys.argv[2], json.loads(sys.argv[3]))
        return
    if action == "status":
        print(json.dumps(status()))
        return
    if action == "toggle":
        action = "stop" if status()["running"] else "region"
    result = stop() if action == "stop" else start(action)
    if result:
        print(result)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(str(error), file=sys.stderr)
        notify("Recording failed", str(error))
        sys.exit(1)
