// Local-noon dates avoid daylight-saving transitions around midnight.
function monthDays(year, month, weekStart) {
    const first = new Date(year, month, 1, 12);
    const offset = (first.getDay() - weekStart + 7) % 7;
    const days = new Date(year, month + 1, 0, 12).getDate();
    const count = Math.ceil((offset + days) / 7) * 7;
    return Array.from({length: count}, (_, index) => new Date(year, month, index - offset + 1, 12));
}

function sameDay(left, right) {
    return left.getFullYear() === right.getFullYear()
        && left.getMonth() === right.getMonth() && left.getDate() === right.getDate();
}
