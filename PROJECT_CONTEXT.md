# NBA Analytics Dashboard — Project Context

## Developer
Kravion Williams

## Project Goal
Build an ESPN/StatMuse-inspired NBA analytics dashboard using Flask, Python, HTML, CSS, Chart.js, and the NBA API.

The goal is to create a polished portfolio project that demonstrates full-stack development, API integration, data processing, dynamic templates, charts, and clean UI design.

## Tech Stack
- Python
- Flask
- nba_api
- Pandas
- HTML
- CSS
- Jinja templates
- Chart.js
- Git/GitHub

## Current Features
- Homepage with ESPN-style design
- Sticky navigation bar
- Player search
- Smart search results for duplicate names
- Trending Players quick search
- Player profile cards
- NBA player headshots
- NBA team logos
- Full team names
- Season averages:
  - PPG
  - RPG
  - APG
  - FG%
  - 3PT%
  - FT%
- Career totals:
  - Points
  - Rebounds
  - Assists
- Season-by-season career table
- Interactive PPG chart with Chart.js
- Compare Players page
- Side-by-side player comparison
- Winner highlighting in comparison table
- Dedicated player profile page at `/player/<player_name>`

## Design Direction
The design should feel like a modern sports analytics site, inspired by ESPN, StatMuse, and Basketball Reference.

Keep:
- Dark theme
- Blue accent color
- Card-based layout
- Clean spacing
- Professional typography
- Hover effects
- Responsive design

## Current Roadmap
1. Add smart Similar Players section to player profile pages.
2. Add team pages.
3. Add league leaders.
4. Improve charts with better Chart.js styling.
5. Add radar chart for player comparison.
6. Add favorites.
7. Add mobile responsiveness.
8. Improve README.
9. Deploy to Render.

## Current Best Next Feature
Build a Similar Players section on each player profile page.

Example:
- Stephen Curry → Damian Lillard, Klay Thompson, Trae Young, Luka Doncic
- LeBron James → Kevin Durant, Giannis Antetokounmpo, Jayson Tatum, Luka Doncic
- Nikola Jokic → Joel Embiid, Giannis Antetokounmpo, Anthony Davis, Victor Wembanyama

The section should feel intelligent and sports-site-like, not random.