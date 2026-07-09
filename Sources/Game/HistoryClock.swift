import Foundation

struct HistoricalEvent {
    let year: Int
    let month: Int
    let day: Int
    let title: String
    let details: String
    let tag: String?

    init(_ year: Int, _ month: Int, _ day: Int, _ title: String, _ details: String, tag: String? = nil) {
        self.year = year
        self.month = month
        self.day = day
        self.title = title
        self.details = details
        self.tag = tag
    }
}

/// In-game calendar. Dates are kept in the Julian calendar ("old style"),
/// as they were in the Russian Empire. 1896 is a leap year in both calendars.
final class HistoryClock {
    private(set) var year = 1894
    private(set) var month = 1
    private(set) var day = 1
    private(set) var hour: Double = 11

    /// Real seconds per one in-game day at 1x speed.
    var secondsPerDay: Double = 8
    var speedMultiplier: Double = 1
    var isRunning = false

    static let monthNames = ["января", "февраля", "марта", "апреля", "мая", "июня",
                             "июля", "августа", "сентября", "октября", "ноября", "декабря"]

    var dateString: String {
        return "\(day) \(HistoryClock.monthNames[month - 1]) \(year) г."
    }

    private func daysIn(month: Int, year: Int) -> Int {
        switch month {
        case 1, 3, 5, 7, 8, 10, 12: return 31
        case 4, 6, 9, 11: return 30
        default: return year % 4 == 0 ? 29 : 28
        }
    }

    /// Advances the clock and returns any historical events whose date was reached.
    func advance(dt: Double) -> [HistoricalEvent] {
        guard isRunning else { return [] }
        var fired: [HistoricalEvent] = []
        hour += dt * speedMultiplier * 24.0 / secondsPerDay
        while hour >= 24 {
            hour -= 24
            day += 1
            if day > daysIn(month: month, year: year) {
                day = 1
                month += 1
                if month > 12 {
                    month = 1
                    year += 1
                }
            }
            let y = year, m = month, d = day
            fired.append(contentsOf: GameData.events.filter { $0.year == y && $0.month == m && $0.day == d })
        }
        return fired
    }
}
