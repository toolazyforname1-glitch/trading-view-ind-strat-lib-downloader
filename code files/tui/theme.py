"""Design tokens and Textual CSS for the Pine Harvester TUI."""
from __future__ import annotations

PALETTE = {
    "bg": "#0B0F14",
    "surface": "#121820",
    "surface2": "#18212B",
    "surface3": "#1E2A36",
    "border": "#243040",
    "accent": "#58A6FF",
    "accent2": "#BC8CFF",
    "success": "#3FB950",
    "warning": "#D29922",
    "danger": "#F85149",
    "text": "#E6EDF3",
    "muted": "#8B949E",
}

P = PALETTE

CSS = f"""
Screen {{
    background: {P['bg']};
    color: {P['text']};
}}
Header {{
    background: {P['surface']};
    color: {P['text']};
}}
Header .header--title {{ color: {P['accent']}; text-style: bold; }}
Header .header--subtitle {{ color: {P['muted']}; }}
Footer {{
    background: {P['surface']};
    color: {P['muted']};
}}

#toolbar {{
    height: 3;
    padding: 0 1;
    background: {P['bg']};
    display: none;
}}
#toolbar Button {{
    height: 3;
    min-width: 12;
    margin-right: 1;
}}

#overview {{ height: 5; }}
.card {{
    width: 1fr;
    height: 5;
    background: {P['surface']};
    border: round {P['border']};
    padding: 0 1;
    content-align: center middle;
    border-title-color: {P['accent']};
    border-title-style: bold;
    border-title-align: left;
}}
.card.flash {{
    background: {P['surface3']};
    border: round {P['accent']};
}}
.card:hover {{
    background: {P['surface2']};
    border: round {P['accent']};
}}

#body {{ height: 1fr; }}
#main {{ width: 1fr; }}
#progress {{
    height: 5;
    background: {P['surface']};
    border: round {P['border']};
    padding: 0 1;
    border-title-color: {P['muted']};
    border-title-style: bold;
}}
#progress.running {{
    border: round {P['accent']};
    background: {P['surface2']};
    border-title-color: {P['accent']};
}}
#progrow {{ height: 1; }}
#spin {{ width: 2; height: 1; color: {P['accent']}; }}
#jobtitle {{ width: 1fr; height: 1; content-align: left middle; }}
#spark {{ width: 22; height: 1; }}
#badge {{ width: auto; height: 1; padding: 0 1; }}
#progbar {{ height: 1; margin-top: 1; }}
#meta {{ height: 1; color: {P['muted']}; }}

#logpanel {{
    height: 1fr;
    background: {P['surface']};
    border: round {P['border']};
    border-title-color: {P['muted']};
    border-title-style: bold;
}}
#logpanel.flash-success {{ border: round {P['success']}; }}
#logpanel.flash-error {{ border: round {P['danger']}; }}
#log {{ height: 1fr; background: {P['bg']}; padding: 0 1; }}
#logfilter {{ height: 1; display: none; }}
#logquery {{ width: 1fr; height: 1; border: none; background: {P['surface2']}; padding: 0 1; }}
#logfilterhint {{ width: auto; padding: 0 1; color: {P['muted']}; content-align: right middle; }}
#queue-panel.flash {{ border: round {P['accent']}; background: {P['surface2']}; }}
#growth {{ height: 1; width: 100%; }}

#sidebar {{
    width: 40;
    margin-left: 1;
    display: none;
}}
.panel {{
    height: 8;
    background: {P['surface']};
    border: round {P['border']};
    padding: 0 1;
    border-title-color: {P['muted']};
    border-title-style: bold;
}}
#data-panel {{ height: 1fr; }}

#statusbar {{ height: 1; background: {P['surface']}; }}
#status-left {{ width: 1fr; height: 1; padding: 0 1; content-align: left middle; }}
#status-right {{ width: auto; height: 1; padding: 0 1; color: {P['muted']}; content-align: right middle; }}

SearchScreen {{ align: center middle; }}
#searchbox {{
    width: 90%;
    max-width: 120;
    height: 74%;
    background: {P['surface']};
    border: round {P['accent']};
    padding: 1 2;
    border-title-color: {P['accent']};
    border-title-style: bold;
}}
#q {{ height: 3; }}
#searchload {{ height: 1; width: 2; color: {P['accent']}; }}
#results {{ height: 1fr; }}
#hint {{ height: 1; color: {P['muted']}; }}

PaletteScreen {{ align: center middle; }}
#palettebox {{
    width: 74;
    height: 60%;
    max-height: 22;
    background: {P['surface']};
    border: round {P['accent2']};
    padding: 1 2;
    border-title-color: {P['accent2']};
    border-title-style: bold;
}}
#pquery {{ height: 3; }}
#poptions {{ height: 1fr; background: {P['surface']}; border: none; }}
#phint {{ height: 1; color: {P['muted']}; }}

DetailsScreen {{ align: center middle; }}
#detailsbox {{
    width: 90%;
    max-width: 84;
    height: 22;
    background: {P['surface']};
    border: round {P['accent']};
    padding: 1 2;
    border-title-color: {P['accent']};
    border-title-style: bold;
}}
#details {{ height: 1fr; }}
#detailhint {{ height: 1; color: {P['muted']}; }}

ConfirmQuit {{ align: center middle; }}
#quitbox {{
    width: 54;
    height: 11;
    background: {P['surface']};
    border: round {P['danger']};
    padding: 1 2;
}}
#quittext {{ height: 3; }}
#quitbox .buttons {{ height: 3; align: center middle; }}
#quitbox Button {{ margin: 0 1; }}

HistoryScreen {{ align: center middle; }}
#historybox {{
    width: 90%;
    max-width: 92;
    height: 70%;
    background: {P['surface']};
    border: round {P['accent2']};
    padding: 1 2;
    border-title-color: {P['accent2']};
    border-title-style: bold;
}}
#historytable {{ height: 1fr; }}
#historyhint {{ height: 1; color: {P['muted']}; }}

ConfigureScreen {{ align: center middle; }}
#configurebox {{
    width: 90%;
    max-width: 92;
    height: 8;
    background: {P['surface']};
    border: round {P['accent']};
    padding: 1 2;
    border-title-color: {P['accent']};
    border-title-style: bold;
}}
#cpath {{ height: 3; }}
#chint {{ height: 1; color: {P['muted']}; }}

MaintenanceScreen {{ align: center middle; }}
#maintenancebox {{
    width: 90%;
    max-width: 94;
    height: 90%;
    background: {P['surface']};
    border: round {P['warning']};
    padding: 1 2;
    border-title-color: {P['warning']};
    border-title-style: bold;
}}
#msummary {{ height: 7; }}
#moptions {{ height: 1fr; background: {P['surface']}; border: none; }}
#mhint {{ height: 1; color: {P['muted']}; }}

DangerScreen {{ align: center middle; }}
#dangerbox {{
    width: 90%;
    max-width: 86;
    height: 18;
    background: {P['surface']};
    border: round {P['danger']};
    padding: 1 2;
    border-title-color: {P['danger']};
    border-title-style: bold;
}}
#dangertext {{ height: 1fr; }}
#dconfirm {{ height: 3; }}
#dbuttons {{ height: 3; align: center middle; }}
#dbuttons Button {{ margin: 0 1; }}
#dangerhint {{ height: 1; color: {P['muted']}; }}

HelpScreen {{ align: center middle; }}
#helpbox {{
    width: 90%;
    max-width: 76;
    height: 90%;
    max-height: 26;
    background: {P['surface']};
    border: round {P['accent']};
    padding: 1 2;
    border-title-color: {P['accent']};
    border-title-style: bold;
}}
#helptext {{ height: 1fr; }}
"""
