pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import Quickshell
import Quickshell.Wayland
import Quickshell.Networking
import Quickshell.Bluetooth
import Quickshell.Services.Pipewire
import Quickshell.Services.UPower
import Luna as Luna
import "components"
import "Status.js" as Status

PanelWindow {
    id: panel
    property int topOffset: 32
    property string page: "main"
    property string returnControl: ""
    property var passwordNetwork: null
    property var scanningDevices: []
    property var discoveryAdapter: null
    readonly property string pageTitle: ({main: "", wifi: "Wi-Fi", bluetooth: "Bluetooth", sound: "Sound", battery: "Power"})[page] || ""

    // Walk the visible page so dynamic device rows participate in focus wrapping.
    function controls() {
        const result = [];
        function visit(item) {
            if (!item.visible || !item.enabled) return;
            if (item.activeFocusOnTab) result.push(item);
            for (const child of item.children) visit(child);
        }
        visit(body);
        return result;
    }
    function stepFocus(direction) {
        const items = controls();
        if (!items.length) return;
        const current = items.findIndex(item => item.activeFocus);
        const next = items[(current + direction + items.length) % items.length];
        next.forceActiveFocus(Qt.TabFocusReason);
        const y = next.mapToItem(body, 0, 0).y;
        const view = scroll.contentItem;
        if (y < view.contentY) view.contentY = y;
        else if (y + next.height > view.contentY + scroll.availableHeight)
            view.contentY = y + next.height - scroll.availableHeight;
    }
    function stopScanning() {
        for (const device of scanningDevices) if (device) device.scannerEnabled = false;
        scanningDevices = [];
        if (discoveryAdapter) discoveryAdapter.discovering = false;
        discoveryAdapter = null;
    }
    function navigate(destination) {
        stopScanning();
        passwordNetwork = null;
        Desktop.error = "";
        page = destination;
        if (destination === "wifi" && Desktop.wifiEnabled) {
            scanningDevices = Desktop.wifiDevices.filter(device => !device.scannerEnabled);
            for (const device of scanningDevices) device.scannerEnabled = true;
        }
        scroll.contentItem.contentY = 0;
        focusDelay.restart();
    }
    function open() {
        Desktop.refreshBrightness();
        Desktop.refreshPowerProfiles();
        returnControl = "";
        visible = true;
        navigate("main");
    }
    function dismiss() {
        visible = false;
    }
    function back() {
        if (passwordNetwork) {
            passwordNetwork = null;
            focusDelay.restart();
        } else if (page !== "main") {
            returnControl = page + "Details";
            navigate("main");
        } else dismiss();
    }
    function chooseNetwork(network) {
        Desktop.error = "";
        passwordNetwork = null;
        if (network.connected) network.disconnect();
        else if (network.known || network.security === WifiSecurityType.Open || network.security === WifiSecurityType.Owe)
            network.connect();
        else if ([WifiSecurityType.WpaPsk, WifiSecurityType.Wpa2Psk, WifiSecurityType.Sae].includes(network.security)) {
            passwordNetwork = network;
            focusDelay.restart();
        } else Desktop.error = "This network requires an enterprise or legacy Wi-Fi profile. Add it in your network settings first.";
    }
    onVisibleChanged: {
        if (!visible) {
            focusDelay.stop();
            stopScanning();
            passwordNetwork = null;
            page = "main";
        }
    }
    Connections {
        target: Desktop
        function onWifiEnabledChanged() {
            if (panel.visible && panel.page === "wifi") panel.navigate("wifi");
        }
    }
    Component.onDestruction: stopScanning()

    WlrLayershell.keyboardFocus: visible ? WlrKeyboardFocus.Exclusive : WlrKeyboardFocus.None
    WlrLayershell.layer: WlrLayer.Overlay
    WlrLayershell.namespace: "luna-control-center"
    color: "transparent"
    exclusionMode: ExclusionMode.Ignore
    visible: false
    anchors { bottom: true; left: true; right: true; top: true }

    Timer {
        id: focusDelay
        interval: 50
        onTriggered: {
            if (!panel.visible) return;
            const items = panel.controls();
            const target = items.find(item => item.objectName === (panel.passwordNetwork ? "wifiPassword" : panel.returnControl)) || items[0];
            if (target) target.forceActiveFocus(Qt.TabFocusReason);
            panel.returnControl = "";
        }
    }
    Shortcut {
        enabled: panel.visible
        context: Qt.ApplicationShortcut
        sequence: "Escape"
        onActivated: panel.back()
        onActivatedAmbiguously: panel.back()
    }
    Shortcut { enabled: panel.visible; sequence: "Alt+Left"; onActivated: panel.back() }
    Shortcut { enabled: panel.visible; sequence: "Tab"; onActivated: panel.stepFocus(1) }
    Shortcut { enabled: panel.visible; sequence: "Shift+Tab"; onActivated: panel.stepFocus(-1) }
    Shortcut { enabled: panel.visible; sequence: "Down"; onActivated: panel.stepFocus(1) }
    Shortcut { enabled: panel.visible; sequence: "Up"; onActivated: panel.stepFocus(-1) }
    MouseArea {
        anchors.fill: parent
        acceptedButtons: Qt.AllButtons
        onPressed: panel.dismiss()
    }

    component VolumeControl: RowLayout {
        property bool microphone: false
        readonly property var node: microphone ? Desktop.source : Desktop.sink
        readonly property bool available: microphone ? Desktop.microphoneAvailable : Desktop.audioAvailable
        Layout.fillWidth: true
        ActionButton {
            Layout.preferredWidth: 30
            enabled: parent.available
            symbol: parent.microphone ? (parent.node && parent.node.audio && parent.node.audio.muted ? "mic-off" : "mic") : Desktop.volumeIcon
            Accessible.name: parent.microphone ? "Toggle microphone mute" : "Toggle sound mute"
            onClicked: parent.node.audio.muted = !parent.node.audio.muted
        }
        LevelSlider {
            Layout.fillWidth: true
            enabled: parent.available
            Accessible.name: parent.microphone ? "Microphone level" : "Volume"
            value: parent.available ? parent.node.audio.volume : 0
            onMoved: parent.node.audio.volume = value
        }
        ControlLabel {
            Layout.fillWidth: false
            Layout.preferredWidth: 34
            text: parent.available ? Math.round(parent.node.audio.volume * 100) + "%" : "—"
        }
    }
    Rectangle {
        id: card
        anchors.right: parent.right
        anchors.rightMargin: Luna.Theme.outerGap
        anchors.top: parent.top
        anchors.topMargin: panel.topOffset + Luna.Theme.outerGap
        border.color: Luna.Theme.muted
        border.width: Luna.Theme.borderWidth
        color: Luna.Theme.background
        height: Math.min(body.implicitHeight + 28, Math.max(0, panel.height - y - Luna.Theme.outerGap))
        radius: Math.min(Luna.Theme.barRounding, width / 2, height / 2)
        width: Math.min(320, panel.width - 2 * Luna.Theme.outerGap)
        clip: true
        MouseArea { anchors.fill: parent; acceptedButtons: Qt.AllButtons }
        ScrollView {
            id: scroll
            anchors.fill: parent
            anchors.margins: 14
            contentWidth: availableWidth
            contentHeight: body.implicitHeight
            ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
            ColumnLayout {
                id: body
                width: scroll.availableWidth
                spacing: 14
                RowLayout {
                    visible: panel.page !== "main"
                    Layout.fillWidth: true
                    ActionButton {
                        Layout.preferredWidth: 34
                        symbol: "chevron-left"
                        Accessible.name: "Back"
                        onClicked: panel.back()
                    }
                    ControlLabel { text: panel.pageTitle; font.pixelSize: 16; font.weight: Font.Medium }
                }
                Loader {
                    Layout.fillWidth: true
                    sourceComponent: panel.page === "wifi" ? wifiPage : panel.page === "bluetooth" ? bluetoothPage
                        : panel.page === "sound" ? soundPage : panel.page === "battery" ? batteryPage : mainPage
                }
                ControlLabel { text: Desktop.error; visible: text !== "" }
            }
        }
    }
    Component {
        id: mainPage
        ColumnLayout {
            spacing: 12
            GridLayout {
                Layout.fillWidth: true
                columns: 2
                columnSpacing: 8
                rowSpacing: 8
                ControlTile {
                    objectName: "wifi"
                    Layout.fillWidth: true
                    Layout.preferredWidth: 1
                    visible: Desktop.wifiAvailable
                    title: "Wi-Fi"
                    description: !Desktop.wifiHardwareEnabled ? "Hardware blocked" : Desktop.connectedNetwork ? Desktop.connectedNetwork.name : ""
                    symbol: Desktop.wifiIcon
                    selected: Desktop.wifiEnabled
                    actionEnabled: Desktop.wifiHardwareEnabled
                    onActivated: Desktop.toggleWifi()
                    onDetailsRequested: panel.navigate("wifi")
                }
                ControlTile {
                    objectName: "bluetooth"
                    Layout.fillWidth: true
                    Layout.preferredWidth: 1
                    visible: !!Desktop.adapter
                    title: "Bluetooth"
                    description: Desktop.connectedBluetooth.map(device => device.name).join(", ")
                    symbol: Desktop.bluetoothIcon
                    selected: Desktop.bluetoothEnabled
                    onActivated: Desktop.toggleBluetooth()
                    onDetailsRequested: panel.navigate("bluetooth")
                }
                ControlTile {
                    objectName: "sound"
                    Layout.fillWidth: true
                    Layout.preferredWidth: 1
                    title: "Sound"
                    symbol: Desktop.volumeIcon
                    selected: Desktop.audioAvailable && !Desktop.muted
                    actionEnabled: Desktop.audioAvailable
                    onActivated: Desktop.toggleMute()
                    onDetailsRequested: panel.navigate("sound")
                }
                ControlTile {
                    objectName: "battery"
                    Layout.fillWidth: true
                    Layout.preferredWidth: 1
                    title: Desktop.hasBattery ? Desktop.batteryText : "Power"
                    symbol: Desktop.batteryIcon
                    selected: Desktop.charging
                    onActivated: panel.navigate("battery")
                    onDetailsRequested: panel.navigate("battery")
                }
            }
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 2
                VolumeControl {}
                RowLayout {
                    Layout.fillWidth: true
                    visible: Desktop.brightnessAvailable
                    Item {
                        Layout.preferredWidth: 30
                        Layout.preferredHeight: 30
                        Luna.Icon { anchors.centerIn: parent; implicitWidth: 14; implicitHeight: 14; name: "sun" }
                    }
                    LevelSlider {
                        Layout.fillWidth: true
                        Accessible.name: "Brightness"
                        from: 1; to: 100; stepSize: 5
                        value: Desktop.brightness
                        onMoved: Desktop.setBrightness(value)
                    }
                    ControlLabel { Layout.fillWidth: false; Layout.preferredWidth: 34; text: Desktop.brightness + "%" }
                }
            }
            MediaCard {
                Layout.fillWidth: true
                media: Media
                visible: Media.available
            }
        }
    }
    Component {
        id: wifiPage
        ColumnLayout {
            spacing: 10
            ActionButton {
                Layout.fillWidth: true
                symbol: Desktop.wifiIcon
                text: Desktop.wifiHardwareEnabled ? "Wi-Fi" : "Hardware blocked"
                selected: Desktop.wifiEnabled
                enabled: Desktop.wifiAvailable && Desktop.wifiHardwareEnabled
                onClicked: { Desktop.toggleWifi(); panel.navigate("wifi"); }
            }
            ControlLabel { visible: !Desktop.wifiAvailable; text: "No Wi-Fi adapter" }
            ControlLabel { visible: Desktop.wifiEnabled && Desktop.networks.length === 0; text: "Looking for networks…" }
            Repeater {
                model: Desktop.wifiEnabled ? Desktop.networks : []
                delegate: ActionButton {
                    id: networkButton
                    required property var modelData
                    Layout.fillWidth: true
                    selected: modelData.connected
                    enabled: !modelData.stateChanging
                    symbol: Status.wifiIcon(true, true, modelData.signalStrength)
                    text: modelData.name + (modelData.stateChanging ? " …" : "")
                    Accessible.name: text + (modelData.connected ? ", connected" : "") + ", " + Math.round(modelData.signalStrength * 100) + "% signal"
                    onClicked: panel.chooseNetwork(modelData)
                    Connections {
                        target: networkButton.modelData
                        function onConnectionFailed(reason) {
                            Desktop.error = ConnectionFailReason.toString(reason);
                            if (reason === ConnectionFailReason.NoSecrets) panel.chooseNetworkForPassword(networkButton.modelData);
                        }
                    }
                }
            }
            Loader {
                Layout.fillWidth: true
                active: !!panel.passwordNetwork
                sourceComponent: ColumnLayout {
                    ControlLabel { text: panel.passwordNetwork ? panel.passwordNetwork.name : "" }
                    TextField {
                        id: password
                        objectName: "wifiPassword"
                        Layout.fillWidth: true
                        Accessible.name: "Wi-Fi password"
                        placeholderText: "Password"
                        echoMode: TextInput.Password
                        color: Luna.Theme.foreground
                        font.family: Luna.Theme.uiFont
                        background: Rectangle { color: Luna.Theme.lighterBackground; radius: Luna.Theme.barRounding; border.color: Luna.Theme.accent; border.width: password.activeFocus ? 1 : 0 }
                        onAccepted: connectButton.clicked()
                    }
                    ActionButton {
                        id: connectButton
                        Layout.fillWidth: true
                        text: "Connect"
                        symbol: "wifi"
                        enabled: password.text.length > 0 && !!panel.passwordNetwork
                        onClicked: {
                            if (!enabled) return;
                            panel.passwordNetwork.connectWithPsk(password.text);
                            password.text = "";
                            panel.passwordNetwork = null;
                            panel.focusDelayRestart();
                        }
                    }
                }
            }
        }
    }
    function chooseNetworkForPassword(network) {
        if ([WifiSecurityType.WpaPsk, WifiSecurityType.Wpa2Psk, WifiSecurityType.Sae].includes(network.security)) {
            passwordNetwork = network;
            focusDelay.restart();
        }
    }
    function focusDelayRestart() { focusDelay.restart(); }
    Component {
        id: bluetoothPage
        ColumnLayout {
            spacing: 10
            ActionButton {
                Layout.fillWidth: true
                symbol: Desktop.bluetoothIcon
                text: "Bluetooth"
                selected: Desktop.bluetoothEnabled
                enabled: !!Desktop.adapter
                onClicked: Desktop.toggleBluetooth()
            }
            Repeater {
                model: Desktop.bluetoothEnabled ? Desktop.bluetoothDevices.filter(device => device.paired) : []
                delegate: ActionButton {
                    required property var modelData
                    Layout.fillWidth: true
                    symbol: modelData.connected ? "bluetooth-connected" : "bluetooth"
                    selected: modelData.connected
                    enabled: modelData.state !== BluetoothDeviceState.Connecting && modelData.state !== BluetoothDeviceState.Disconnecting
                    text: modelData.name + (modelData.state === BluetoothDeviceState.Connecting || modelData.state === BluetoothDeviceState.Disconnecting ? " …" : "")
                        + (modelData.batteryAvailable ? " · " + Math.round(modelData.battery * 100) + "%" : "")
                    Accessible.name: text + (modelData.connected ? ", connected" : ", disconnected")
                    onClicked: modelData.connected = !modelData.connected
                }
            }
            ActionButton {
                Layout.fillWidth: true
                visible: Desktop.bluetoothEnabled
                symbol: "search"
                text: Desktop.adapter && Desktop.adapter.discovering ? "Stop scanning" : "Find devices"
                onClicked: {
                    if (Desktop.adapter.discovering) {
                        Desktop.adapter.discovering = false;
                        panel.discoveryAdapter = null;
                    } else {
                        panel.discoveryAdapter = Desktop.adapter;
                        Desktop.adapter.discovering = true;
                    }
                }
            }
            Repeater {
                model: Desktop.bluetoothEnabled ? Desktop.bluetoothDevices.filter(device => !device.paired) : []
                delegate: ActionButton {
                    required property var modelData
                    Layout.fillWidth: true
                    symbol: "bluetooth"
                    text: modelData.name + (modelData.pairing ? " · Cancel pairing" : " · Pair")
                    onClicked: modelData.pairing ? modelData.cancelPair() : modelData.pair()
                }
            }
        }
    }
    Component {
        id: soundPage
        ColumnLayout {
            spacing: 10
            ControlLabel { text: "Output" }
            VolumeControl {}
            Repeater {
                model: Desktop.outputs
                delegate: ActionButton {
                    required property var modelData
                    Layout.fillWidth: true
                    text: modelData.description || modelData.name
                    symbol: modelData === Desktop.sink ? "check" : "volume-2"
                    selected: modelData === Desktop.sink
                    onClicked: Pipewire.preferredDefaultAudioSink = modelData
                }
            }
            ControlLabel { visible: !Desktop.outputs.length; text: "No output devices" }
            ControlLabel { text: "Microphone" }
            VolumeControl { microphone: true }
            Repeater {
                model: Desktop.inputs
                delegate: ActionButton {
                    required property var modelData
                    Layout.fillWidth: true
                    text: modelData.description || modelData.name
                    symbol: modelData === Desktop.source ? "check" : "mic"
                    selected: modelData === Desktop.source
                    onClicked: Pipewire.preferredDefaultAudioSource = modelData
                }
            }
            ControlLabel { visible: !Desktop.inputs.length; text: "No microphones" }
        }
    }
    Component {
        id: batteryPage
        ColumnLayout {
            spacing: 12
            RowLayout {
                Luna.Icon { name: Desktop.batteryIcon; implicitWidth: 14; implicitHeight: 14 }
                ControlLabel { text: Desktop.batteryText; font.pixelSize: 20 }
            }
            ControlLabel { text: Desktop.batteryRemaining; visible: text !== "" }
            ProgressBar {
                id: batteryLevel
                Layout.fillWidth: true
                visible: Desktop.hasBattery
                value: Desktop.hasBattery ? Desktop.battery.percentage : 0
                background: Rectangle { implicitHeight: 6; color: Luna.Theme.muted; radius: Luna.Theme.barRounding }
                contentItem: Item {
                    implicitHeight: 6
                    Rectangle { width: parent.width * batteryLevel.visualPosition; height: parent.height; color: Luna.Theme.accent; radius: Luna.Theme.barRounding }
                }
            }
            ControlLabel { visible: Desktop.powerProfilesAvailable; text: "Power mode" }
            Repeater {
                model: Desktop.powerProfilesAvailable ? [
                    {label: "Power saver", icon: "leaf", profile: PowerProfile.PowerSaver},
                    {label: "Balanced", icon: "sliders-horizontal", profile: PowerProfile.Balanced},
                    {label: "Performance", icon: "zap", profile: PowerProfile.Performance}
                ] : []
                delegate: ActionButton {
                    required property var modelData
                    Layout.fillWidth: true
                    visible: modelData.profile !== PowerProfile.Performance || PowerProfiles.hasPerformanceProfile
                    text: modelData.label
                    symbol: modelData.icon
                    selected: PowerProfiles.profile === modelData.profile
                    onClicked: PowerProfiles.profile = modelData.profile
                }
            }
        }
    }
}
