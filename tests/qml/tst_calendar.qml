import QtQuick
import QtTest
import "../../src/luna-bar/Calendar.js" as Calendar

TestCase {
    name: "Calendar"

    function test_leap_year_and_week_alignment() {
        const leap = Calendar.monthDays(2024, 1, 1);
        compare(leap[0].getDay(), 1);
        compare(leap.filter(day => day.getMonth() === 1).length, 29);
        const normal = Calendar.monthDays(2025, 1, 0);
        compare(normal[0].getDay(), 0);
        compare(normal.filter(day => day.getMonth() === 1).length, 28);
        compare(leap.length % 7, 0);
        compare(normal.length % 7, 0);
    }
    function test_year_boundary_and_complete_weeks() {
        const cells = Calendar.monthDays(2027, 0, 1);
        compare(cells[0].getFullYear(), 2026);
        compare(cells[0].getMonth(), 11);
        compare(cells.filter(day => day.getMonth() === 0).length, 31);
        for (let i = 1; i < cells.length; i++) {
            const expected = new Date(cells[i - 1]);
            expected.setDate(expected.getDate() + 1);
            verify(Calendar.sameDay(expected, cells[i]));
        }
    }
    function test_same_day_ignores_time() {
        verify(Calendar.sameDay(new Date(2026, 9, 12, 1), new Date(2026, 9, 12, 23)));
        verify(!Calendar.sameDay(new Date(2026, 9, 12), new Date(2026, 9, 13)));
    }
}
