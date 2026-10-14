# Recording

`luna record region` selects an area; `luna record screen` records the focused
monitor. `luna record stop` finishes the current file. `luna record toggle` stops
an active recording or starts region selection. `luna record status` prints JSON
without starting a recording.

Trigger → Screen Recording offers the same actions. Super + Print toggles region
recording and Super + Shift + Print stops it. A red Stop control stays visible
above fullscreen windows until saving finishes.

Recordings use wf-recorder with software H.264 at 30 fps and save timestamped MP4
files under `~/Videos/Recordings`. Set `LUNA_RECORDING_DIR` to change the location.
Capture is silent; it does not record the microphone or system sound. Escape
cancels region selection without creating a video. The menu closes before capture.
Click the saved notification to open the recording in the default video player.

A session worker owns the recorder, serializes starts, and tracks its identity in
`$XDG_RUNTIME_DIR/luna-recording`. Stop targets only that worker and lets the video
finish writing. An existing recording survives a bar reload. Capture errors appear
as notifications, and diagnostic output stays in that runtime directory.
