# Scraping course data from bulletin pdf file

- Bulletin is located at etl/2025-26-bulletin.pdf
- Courses are often under a larger font "Courses" section
- Sometimes, the "Courses" section is followed by another sub heading, after which the list of courses actually begins
- We want to extract course listings and descriptions
  - For example:
    - listing/title: BIOL 3663. IMS-3 Pulmonary.
    - description: No description available.
- Notice that many courses might say "no description available"
- Extract into a json, with:
  - title
  - decription
  - source (this will be the same for all. source="bulletin")
