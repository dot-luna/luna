import QtQuick
import QtTest
import "../../../../src/luna-bar/bluetooth/PairingLogic.js" as Logic

TestCase {
    name: "BluetoothPairing"

    function test_pin_and_numeric_passkey_validation() {
        compare(Logic.validInput({kind: "pin"}, "aB-123"), true);
        compare(Logic.validInput({kind: "pin"}, "12345678901234567"), false);
        compare(Logic.validInput({kind: "pin"}, ""), false);
        compare(Logic.validInput({kind: "pin"}, "123\n"), false);
        ["0", "000001", "999999"].forEach(value => compare(Logic.validInput({kind: "passkey"}, value), true));
        ["", "-1", "1000000", "12ab", "12\n", "１２３"].forEach(value => compare(Logic.validInput({kind: "passkey"}, value), false));
    }

    function test_only_known_approval_requests_offer_pairing() {
        ["confirm", "authorize", "service"].forEach(kind => compare(Logic.validInput({kind: kind}, ""), true));
        ["display-pin", "display-passkey", "unknown"].forEach(kind => compare(Logic.validInput({kind: kind}, ""), false));
        compare(Logic.validInput(null, ""), false);
        compare(Logic.needsInput(null), false);
        compare(Logic.isDisplay(null), false);
        compare(Logic.needsInput({kind: "passkey"}), true);
        compare(Logic.isDisplay({kind: "display-passkey"}), true);
    }

    function test_instructions_distinguish_entry_confirmation_and_remote_typing() {
        verify(Logic.instructions({kind: "pin"}).startsWith("Enter"));
        verify(Logic.instructions({kind: "confirm"}).includes("both devices"));
        verify(Logic.instructions({kind: "display-passkey"}).startsWith("Type"));
        compare(Logic.instructions(null), "");
        compare(Logic.serviceName("00001124-0000-1000-8000-00805f9b34fb"), "Keyboard or mouse");
        compare(Logic.serviceName("unknown-service"), "unknown-service");
    }
}
