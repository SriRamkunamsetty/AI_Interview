import re

path = r'c:\Users\sagar\Downloads\mock-interview\forenten\admin.html'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Inject toUtcIso helper
helper_code = """        const FRONTEND_BASE = "https://ai-adaptive-interview.vercel.app";

        /**
         * Convert a datetime-local input value (local ISO, no timezone) to a UTC ISO
         * string. Pass-through if already has Z/offset, or if empty.
         */
        function toUtcIso(localDatetimeValue) {
            if (!localDatetimeValue) return '';
            if (localDatetimeValue.endsWith('Z') || localDatetimeValue.includes('+')) return localDatetimeValue;
            const d = new Date(localDatetimeValue);  // browser interprets as LOCAL time
            if (isNaN(d.getTime())) return localDatetimeValue;
            return d.toISOString();
        }"""
content = content.replace('        const FRONTEND_BASE = "https://ai-adaptive-interview.vercel.app";', helper_code)

# 2. Replace scheduleStart usage
content = content.replace('scheduled_start: scheduleStart,', 'scheduled_start: toUtcIso(scheduleStart),')
content = content.replace('scheduled_end: scheduleEnd', 'scheduled_end: toUtcIso(scheduleEnd)')

# 3. Replace schedStart usage
content = content.replace('scheduled_start: schedStart,', 'scheduled_start: toUtcIso(schedStart),')
content = content.replace('scheduled_end: schedEnd', 'scheduled_end: toUtcIso(schedEnd)')

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)

print("Safely patched admin.html")
