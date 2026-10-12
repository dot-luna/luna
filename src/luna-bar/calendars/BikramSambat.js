// Adapted for QML from medic/bikram-sambat (Apache-2.0).
// Source revision: aeaa7b88332384bddeea98c2445308d437966641
// See LICENSE-bikram-sambat. Luna uses local civil dates and UTC day arithmetic
// instead of upstream string parsing, so conversion is independent of DST.
.pragma library

var monthLengths = [
    5315258, 5314490, 9459438, 8673005, 5315258, 5315066, 9459438, 8673005, 5315258, 5314298,
    9459438, 5327594, 5315258, 5314298, 9459438, 5327594, 5315258, 5314286, 9459438, 5315306,
    5315258, 5314286, 8673006, 5315306, 5315258, 5265134, 8673006, 5315258, 5315258, 9459438,
    8673005, 5315258, 5314298, 9459438, 8673005, 5315258, 5314298, 9459438, 8473322, 5315258,
    5314298, 9459438, 5327594, 5315258, 5314298, 9459438, 5327594, 5315258, 5314286, 8673006,
    5315306, 5315258, 5265134, 8673006, 5315306, 5315258, 9459438, 8673005, 5315258, 5314490,
    9459438, 8673005, 5315258, 5314298, 9459438, 8473325, 5315258, 5314298, 9459438, 5327594,
    5315258, 5314298, 9459438, 5327594, 5315258, 5314286, 9459438, 5315306, 5315258, 5265134,
    8673006, 5315306, 5315258, 5265134, 8673006, 5315258, 5314490, 9459438, 8673005, 5315258,
    5314298, 9459438, 8669933, 5315258, 5314298, 9459438, 8473322, 5315258, 5314298, 9459438,
    5327594, 5315258, 5314286, 9459438, 5315306, 5315258, 5265134, 8673006, 5315306, 5315258,
    5265134, 8673006, 5315258, 5315258, 5527226, 5528046, 5527277, 5528250, 5528057, 5527277,
    5527277,
];
var monthNames = ["Baisakh", "Jestha", "Ashadh", "Shrawan", "Bhadra", "Ashwin",
    "Kartik", "Mangsir", "Poush", "Magh", "Falgun", "Chaitra"];

// The table starts at 1970-01-01 BS, corresponding to 1913-04-13 AD.
// Return null outside its range; never extrapolate month lengths.
function fromDate(date) {
    let days = (Date.UTC(date.getFullYear(), date.getMonth(), date.getDate())
        - Date.UTC(1913, 3, 13)) / 86400000;
    if (!isFinite(days) || days < 0) return null;
    for (let year = 0; year < monthLengths.length; year++) {
        for (let month = 0; month < 12; month++) {
            const length = 29 + ((monthLengths[year] >>> (month * 2)) & 3);
            if (days < length) return {year: 1970 + year, month: month + 1, day: days + 1};
            days -= length;
        }
    }
    return null;
}

function format(date) {
    const bs = fromDate(date);
    return bs ? bs.day + " " + monthNames[bs.month - 1] + " " + bs.year + " BS" : "";
}
