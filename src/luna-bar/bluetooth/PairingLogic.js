function needsInput(request) {
    return !!request && (request.kind === "pin" || request.kind === "passkey");
}

function isDisplay(request) {
    return !!request && (request.kind === "display-pin" || request.kind === "display-passkey");
}

function validInput(request, value) {
    if (!request || isDisplay(request))
        return false;
    if (request.kind === "pin")
        return value.length > 0 && value.length <= 16 && !/[\u0000-\u001f\u007f]/.test(value);
    if (request.kind === "passkey")
        return value.length > 0 && value.length <= 6 && !/[^0-9]/.test(value);
    return ["confirm", "authorize", "service"].includes(request.kind);
}

function instructions(request) {
    if (!request)
        return "";
    switch (request.kind) {
    case "pin": return "Enter the PIN shown on this device.";
    case "passkey": return "Enter the passkey shown on this device.";
    case "confirm": return "Confirm that this code appears on both devices.";
    case "display-pin":
    case "display-passkey": return "Type this code on the device, then press Enter.";
    case "authorize": return "Allow this device to pair with your computer?";
    case "service": return "Allow this device to connect?";
    default: return "";
    }
}

function serviceName(uuid) {
    const services = {
        "00001105-0000-1000-8000-00805f9b34fb": "File transfer",
        "0000110a-0000-1000-8000-00805f9b34fb": "Audio source",
        "0000110b-0000-1000-8000-00805f9b34fb": "Audio playback",
        "0000110e-0000-1000-8000-00805f9b34fb": "Media controls",
        "00001112-0000-1000-8000-00805f9b34fb": "Headset audio",
        "0000111e-0000-1000-8000-00805f9b34fb": "Hands-free audio",
        "0000111f-0000-1000-8000-00805f9b34fb": "Hands-free audio gateway",
        "00001124-0000-1000-8000-00805f9b34fb": "Keyboard or mouse"
    };
    return services[uuid] || uuid || "";
}
