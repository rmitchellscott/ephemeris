# Ephemeris
<img src="assets/logo.svg" alt="Ephemeris Icon" width="170" align="right">

> Your daily path through time.

Ephemeris is a Python-based tool that automatically generates clean, daily schedules using ICS calendar data. Designed with e-ink tablets like ReMarkable and Kindle Scribe in mind.

## Features

- **Automated Schedule Generation**: Seamlessly convert ICS calendar data into organized daily planners.
- **Customizable Layout**: Adjust your daily schedule's layout, timeframe, and appearance via environment variables.
- **Elegant PDF Output**: Clean PDFs designed specifically with the e-ink tablets in mind.

## Screenshots

These screenshots broadly show the layout options that are possible. See [Customization](#customization--supported-environment-variables) for more information.

<p float="left">
  <a href="assets/example-default.png">
    <img src="assets/example-default.png" alt="Default Layout" width="200px"/>
  </a>
  <a href="assets/example-grid-only.png">
    <img src="assets/example-grid-only.png" alt="Time Grid Only" width="200px"/>
  </a>
  <a href="assets/example-grid-allday.png">
    <img src="assets/example-grid-allday.png" alt="All Day Full Width" width="200px"/>
  </a>
    <a href="assets/example-centercal.png">
    <img src="assets/example-centercal.png" alt="Single Month Mini-Calendar" width="200px"/>
  </a>
</p>

## Getting Started

### Calendar Configuration

The program uses a YAML configuration file to set up the calendars:
```yaml
calendars:
  - name: Personal
    source: calendars/personal.ics
    color: gray6
  - name: US Holidays
    source: https://www.opm.gov/policy-data-oversight/pay-leave/federal-holidays/holidays.ics
    color: gray4

```
Supported values for colors are CSS names, hex colors, as well as a series of grays (gray1 through gray14) that correspond to each step of 4-bit grayscale. 

### Docker Compose

```yaml
services:
  ephemeris:
    image: ghcr.io/rmitchellscott/ephemeris
    volumes:
      - ./calendars:/app/calendars
      - ./output:/app/output
      - ./config.yaml:/app/config.yaml
      - ./feeds_meta.yaml:/app/feeds_meta.yaml  # Used for change detection
    environment:
      - TIMEZONE=America/Denver
      - DATE_RANGE=week
```

### Docker
```shell
docker run --rm \
  -v "$(pwd)/calendars:/app/calendars" \
  -v "$(pwd)/output:/app/output" \
  -v "$(pwd)/config.yaml:/app/config.yaml" \
  -v "$(pwd)/feeds_meta.yaml:/app/feeds_meta.yaml" \
  -e TIMEZONE=America/Denver \
  -e DATE_RANGE=week \
  ghcr.io/rmitchellscott/ephemeris
```

### Python
#### Setup

- Python 3.8+
- Dependencies: `icalendar`, `reportlab`, `PyPDF2`, `pytz`, `dateutil`, `yaml`

Install dependencies with:

```bash
pip install requirements.txt
```

Set environment variables to customize the output:

```bash
export TIMEZONE="America/New_York"
```
Run the script:

```bash
python ephemeris.py
```

## Customization & Supported Environment Variables

### Time

| Variable       | Default                   | Example          | Description                                                                          |
|:---------------|:--------------------------|:-----------------|:-------------------------------------------------------------------------------------|
| DATE_RANGE     | today           | today, week, month, 2025-04-14:2025-04-18 | Date range to create schedules for. Each day will be a single page. A single multi-page PDF will be rendered.   |
| END_HOUR       | 21              | 21                                 | Defines the ending hour of the displayed daily schedule.  |
| EXCLUDE_BEFORE | 0               | 4                                  | Excludes events with start times before this hour from the generated schedule.                        |
| START_HOUR     | 6               | 6                                  | Defines the starting hour of the displayed daily schedule.   |
| TIMEZONE       | UTC             | America/New_York                   | Sets the timezone used for interpreting event times.   |
| TIME_FORMAT    | 24              | 12, 24                             | Specifies time formatting in 12-hour or 24-hour formats.   |

### Program Behavior

| Variable       | Default                   | Example          | Description                                                                          |
|:---------------|:--------------------------|:-----------------|:-------------------------------------------------------------------------------------|
| FORCE_REFRESH  | false           | true, false                        |      Skip the changed events check and always render a PDF for each run. |
| OUTPUT_PDF     | output/daily_schedule.pdf |                          | Path and name for rendered PDF.  |

### Document Rendering

| Variable       | Default                   | Example          | Description                                                                          |
|:---------------|:--------------------------|:-----------------|:-------------------------------------------------------------------------------------|
| ALLDAY_FROM    | grid            | grid, page                         | Select the left boundry for the "All-Day Events" box, either the main time grid or the left margin.   |
| DRAW_ALL_DAY   | true            | true, false                        | Set to `true` to draw the All Day Events, set to `false` to disable.  |
| DRAW_MINICALS  | full            | full, current, false               | `full` will draw mini-calendars for the current and next month, `current` will draw only the current month, `false` will disable. |
| EVENT_FILL     | gray14          | black,gray0, #000000               | Color for the background of events. CSS names, Ephemeris gray names, and hex supported. |
| EVENT_STROKE   | gray(20%)       | black,gray0, #000000               | Color for the outline of events. CSS names, Ephemeris gray names, and hex supported.     |
| FOOTER         | E P H E M E R I S         | updated, disabled, My Cool Footer  | Set to `updated` to print the "Updated at" timestamp, `disabled` to disable, or any text you want.  |
| FOOTER_COLOR   | gray(60%)       | black,gray0, #000000             | Color for the page footer. CSS names, Ephemeris gray names, and hex supported.   |
| GRIDLINE_COLOR | gray(20%)       | black, #000000                   | Color for the time grid lines. CSS names, Ephemeris gray names, and hex supported.   |
| MINICAL_ALIGN  | right           | center, right, left                | Horizontal alignment for the mini-calenders. Center and Left are available when `DRAW_ALL_DAY` is `false`.  |
| MINICAL_HEIGHT | 60              | 40                                 | Height of mini-calendars and All-Day Events area in points (1pt = 1/72in).   |
| MINICAL_GAP    | 10              | 12                                 | Gap between each calender, and between calendars and other elements. In points (1pt = 1/72in).   |
| PDF_DPI        | 226             | 300                                | DPI/PPI for rendered PDF.   |
| PDF_PAGE_SIZE  | 1872x1404       | 1920x1080                          | Resolution for rendered PDF.   |
| PDF_MARGIN_LEFT        | 6       | 12                                 | Left page margin in points (1pt = 1/72in).   |
| PDF_MARGIN_RIGHT       | 6       | 12                                 | Right page margin in points (1pt = 1/72in).   |
| PDF_MARGIN_TOP         | 9       | 12                                 | Top page margin in points (1pt = 1/72in).   |
| PDF_MARGIN_BOTTOM      | 6       | 12                                 | Bottom page margin in points (1pt = 1/72in).   |
| PDF_GRID_BOTTOM_BUFFER | 9       | 12                                 | Buffer between the bottom of the grid and the bottom margin in points (1pt = 1/72in). Useful for having a footer.  |  

## License

MIT

---

Enjoy precisely organized days with Ephemeris!
