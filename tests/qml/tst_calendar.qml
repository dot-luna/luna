import QtQuick
import QtTest
import "../../src/luna-bar/Calendar.js" as Calendar
import "../../src/luna-bar/calendars/BikramSambat.js" as BS

TestCase {
    name: "Calendar"

    // Known AD/BS pairs from the pinned upstream conversion fixtures.
    function test_bs_boundaries_and_leap_day() {
        compare(BS.format(new Date(1913, 3, 13)), "1 Baisakh 1970 BS");
        compare(BS.format(new Date(2024, 1, 29)), "17 Falgun 2080 BS");
        compare(BS.format(new Date(2025, 3, 13)), "31 Chaitra 2081 BS");
        compare(BS.format(new Date(2025, 3, 14)), "1 Baisakh 2082 BS");
        compare(BS.format(new Date(2026, 3, 13)), "30 Chaitra 2082 BS");
        compare(BS.format(new Date(2026, 3, 14)), "1 Baisakh 2083 BS");
        compare(BS.format(new Date(2026, 9, 12)), "26 Ashwin 2083 BS");
    }
    function test_bs_local_day_and_unsupported_dates() {
        compare(BS.format(new Date(2026, 3, 14, 0, 1)), BS.format(new Date(2026, 3, 14, 23, 59)));
        compare(BS.fromDate(new Date(1913, 3, 12)), null);
        compare(BS.fromDate(new Date(2040, 0, 1)), null);
        compare(BS.format(new Date(NaN)), "");
    }

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
