# Scraping data from Courses at Brown (https://cab.brown.edu/#)

- work in the etl directory

- Use libraries like requests, BeautifulSoup, or playwright

- Need to scrape data for All Courses from Any Term (2025-26) and All Modes of Instruction
- Extract data into course_code, title, instructor, meeting_times, prerequisites, department,
  description, source
- Source will be the same for all; source will be CAB
- Need to search with the these filters:
  - All Courses from Any Term (2025-26) and All Modes of Instruction
  - Leave the keyword input field empty
- After "FIND COURSES" button is clicked, the Search Results column will contain a list of all courses (around 2839 courses)
- Need to go through each course and extract the structured data

From the course pages:

- class="dtl-course-code" contains the course_code
- class="text col-8 detail-title text--huge" contains the title
- class="instructor" contains details regarding the instructor, including class="instructor-name" and class="truncate" which contains the email details
- class="meet" contains meeting time details
- The Registration Restrictions section contains the prerequisites details
