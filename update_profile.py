"""Regenerate dark_mode.svg / light_mode.svg with live GitHub stats.

Runs daily via GitHub Actions. Stdlib only, no dependencies.
"""
import calendar
import html
import json
import os
import sys
import urllib.request
from datetime import date, datetime, timezone

USER = "prashantkmr389"
JOINED_YEAR = 2021  # account creation year
W = 56  # info column width in characters

TOKEN = os.environ.get("GITHUB_TOKEN") or os.environ.get("ACCESS_TOKEN") or ""
PRIV_TOKEN = os.environ.get("ACCESS_TOKEN") or TOKEN

DEV_ART = r"""
                   @@@@@              
                @@@@@@@@@@@@          
               @@@@@@@@@@@@@@         
              @@@@@@@@@@@@@@@@        
             @@@@@@@@@@@@@@@@@@       
             @@@@@@@@@@@@@@@@@@       
             @@@+:  :::**#@@@@        
              @%+**.  :+..#@@         
              #*:+++ :***.%@*         
              ++   .      #:          
              ::  .. .    %           
               +.++++:...::           
               %..:..::. +            
                #.      +             
               @%@*:.:%#%             
              @@::@@@@@:.@            
          @@@@@@% :+*+. .@@@          
       @@@@@@@@@@:.::. .+@@@@#        
     @@@@@@@@@@@@@...   *@@@@@@@      
   @@@@@@@@@@@@@@@*   .+@@@@@@@@@@    
  @@@@@@#@@@@#@@@@% .@@@@@@@@@@@@##   
  @@@@@@#@@@@##@#@@*@@@@@@@@@@#@@@@@@ 
 @@@@@@@#@@@#@@@#@@@@####@@@#@#@@@@@@@
@@@@@#@@##@@#@#@#@#*@#@@#@@@@@@@@@@@@@
@@@@@@@@##@##@@@#@#%@#@###@#@#@@@@#@@@
@@@#@@@@##@#@#@@###@@@@#####@@#@@#@@@@
@@@@@@@@####@#@#@@##@#@#####@@@@@@@@@@
@@@#@@@@@###@#@#@########@##@#@@@@@#@@
"""


def gh(url, payload=None, token=None):
    headers = {"Accept": "application/vnd.github+json"}
    auth = token or TOKEN
    if auth:
        headers["Authorization"] = f"Bearer {auth}"
    headers["User-Agent"] = "Python-Profile-Updater"
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode() if payload else None,
        headers=headers,
    )
    with urllib.request.urlopen(req) as r:
        return r.status, json.loads(r.read() or "{}")


def graphql(query, variables=None, token=None):
    auth = token or TOKEN
    if not auth:
        return None
    _, resp = gh("https://api.github.com/graphql", {"query": query, "variables": variables or {}}, auth)
    if resp.get("errors"):
        print(f"GraphQL warning: {resp['errors']}", file=sys.stderr)
        return resp.get("data")
    return resp.get("data")


def fetch_stats():
    current_year = datetime.now(timezone.utc).year
    stats = {
        "followers": 3,
        "repos": 16,
        "contributed": 5,
        "stars": 12,
        "commits": 521,
        "loc_add": 142500,
        "loc_del": 38200,
        "loc": 104300,
    }

    try:
        if TOKEN:
            yr_aliases = "\n".join(
                f'y{y}: contributionsCollection(from: "{y}-01-01T00:00:00Z", to: "{y + 1}-01-01T00:00:00Z")'
                " { totalCommitContributions restrictedContributionsCount }"
                for y in range(JOINED_YEAR, current_year + 1)
            )
            gdata = graphql(f'query {{ user(login: "{USER}") {{ {yr_aliases} }} }}')
            if gdata and gdata.get("user"):
                contrib = gdata["user"]
                commits = sum(
                    v.get("totalCommitContributions", 0) + v.get("restrictedContributionsCount", 0)
                    for v in contrib.values() if isinstance(v, dict)
                )
                if commits > 0:
                    stats["commits"] = commits

            udata = graphql(f"""
            query {{
              user(login: "{USER}") {{
                id
                followers {{ totalCount }}
                repositories(first: 100, ownerAffiliations: OWNER) {{
                  totalCount
                  nodes {{ name stargazerCount isFork }}
                }}
                repositoriesContributedTo(first: 100, contributionTypes: [COMMIT, PULL_REQUEST, REPOSITORY]) {{
                  totalCount
                }}
              }}
            }}""", token=PRIV_TOKEN)

            if udata and udata.get("user"):
                u = udata["user"]
                stats["followers"] = u["followers"]["totalCount"]
                stats["repos"] = u["repositories"]["totalCount"]
                stats["contributed"] = u["repositoriesContributedTo"]["totalCount"]
                stats["stars"] = sum(n["stargazerCount"] for n in u["repositories"]["nodes"])
                
                loc_info = loc([n["name"] for n in u["repositories"]["nodes"] if not n["isFork"]], u["id"])
                if loc_info["loc_add"] > 0:
                    stats.update(loc_info)
        else:
            _, uinfo = gh(f"https://api.github.com/users/{USER}")
            if uinfo:
                stats["followers"] = uinfo.get("followers", stats["followers"])
                stats["repos"] = uinfo.get("public_repos", stats["repos"])
    except Exception as e:
        print(f"Error fetching stats, using defaults: {e}", file=sys.stderr)

    return stats


LOC_QUERY = """
query($owner: String!, $name: String!, $id: ID!, $cursor: String) {
  repository(owner: $owner, name: $name) {
    defaultBranchRef { target { ... on Commit {
      history(first: 100, author: {id: $id}, after: $cursor) {
        pageInfo { hasNextPage endCursor }
        nodes { additions deletions }
      }
    } } }
  }
}"""


def loc(repo_names, user_id):
    add = rem = 0
    for name in repo_names:
        cursor = None
        try:
            while True:
                gres = graphql(LOC_QUERY, {"owner": USER, "name": name, "id": user_id, "cursor": cursor}, token=PRIV_TOKEN)
                if not gres or not gres.get("repository") or not gres["repository"].get("defaultBranchRef"):
                    break
                ref = gres["repository"]["defaultBranchRef"]
                h = ref["target"]["history"]
                add += sum(n["additions"] for n in h["nodes"])
                rem += sum(n["deletions"] for n in h["nodes"])
                if not h["pageInfo"]["hasNextPage"]:
                    break
                cursor = h["pageInfo"]["endCursor"]
        except Exception as e:
            print(f"loc {name}: {e}", file=sys.stderr)
    return {"loc_add": add, "loc_del": rem, "loc": add - rem}


PALETTES = {
    "dark": {
        "bg": "#0d1117",
        "border": "#30363d",
        "art": "#58a6ff",
        "h": "#36bcf7",
        "k": "#ffa657",
        "v": "#c9d1d9",
        "d": "#484f58",
        "g": "#3fb950",
        "r": "#f85149",
    },
    "light": {
        "bg": "#ffffff",
        "border": "#d0d7de",
        "art": "#0969da",
        "h": "#0969da",
        "k": "#953800",
        "v": "#24292f",
        "d": "#afb8c1",
        "g": "#1a7f37",
        "r": "#cf222e",
    },
}


def kv(key, val, width=W):
    dots = "." * max(width - len(key) - len(str(val)) - 3, 1)
    return [(f"{key}: ", "k"), (dots + " ", "d"), (str(val), "v")]


def kv2(k1, v1, k2, v2):
    left = kv(k1, v1, 30)
    return left + [(" | ", "d")] + kv(k2, v2, 23)


def rule(title=""):
    label = f"─ {title} " if title else ""
    return [(label, "h"), ("─" * (W - len(label)), "d")]


def info_lines(s):
    n = lambda x: f"{x:,}"
    return [
        [(f"{USER.lower()}@github ", "h"), ("─" * (W - len(USER) - 8), "d")],
        [],
        kv("OS", "macOS, Linux"),
        kv("Uptime", "B.Tech CSE, NIT Patna '24"),
        kv("Host", "Bangalore, India"),
        kv("Kernel", "Software Engineer · Full-Stack"),
        kv("IDE", "Claude Code, Antigravity IDE, Cursor"),
        [],
        kv("Languages.Programming", "TypeScript, JavaScript, Python, Java, C++"),
        kv("Focus", "Full-Stack, Fintech & Derivatives, CP"),
        kv("Building", "Vestipy, Trade Signal Share"),
        [],
        rule("Contact"),
        kv("Email", "prashantkmr389@gmail.com"),
        kv("LinkedIn", "in/prashantkmr389"),
        kv("Portfolio", "prashantkmr389-portfolio.vercel.app"),
        [],
        rule("GitHub Stats"),
        kv2("Repos", f"{s['repos']} {{Contributed: {s['contributed']}}}", "Stars", n(s["stars"])),
        kv2("Commits", n(s["commits"]), "Followers", n(s["followers"])),
        [
            ("Lines of Code: ", "k"),
            (n(s["loc"]), "v"),
            (" ( ", "d"),
            (n(s["loc_add"]) + "++", "g"),
            (", ", "d"),
            (n(s["loc_del"]) + "--", "r"),
            (" )", "d"),
        ],
    ]


def render(mode, stats):
    p = PALETTES[mode]
    out = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="840" height="500" viewBox="0 0 840 500" '
        'font-family="Consolas, Menlo, Monaco, monospace" font-size="13px">',
        f'<rect x="0.5" y="0.5" width="839" height="499" rx="10" fill="{p["bg"]}" stroke="{p["border"]}"/>',
    ]
    art_lines = DEV_ART.strip("\n").split("\n")
    for i, line in enumerate(art_lines):
        out.append(f'<text x="25" y="{40 + i * 15}" fill="{p["art"]}" xml:space="preserve">{html.escape(line)}</text>')
    for i, segs in enumerate(info_lines(stats)):
        if not segs:
            continue
        spans = "".join(f'<tspan fill="{p[c]}">{html.escape(t)}</tspan>' for t, c in segs)
        out.append(f'<text x="390" y="{45 + i * 21}" xml:space="preserve">{spans}</text>')
    out.append("</svg>")
    return "\n".join(out)


if __name__ == "__main__":
    stats = fetch_stats()
    print("stats:", stats)
    for mode in PALETTES:
        with open(f"{mode}_mode.svg", "w", encoding="utf-8") as f:
            f.write(render(mode, stats))
    print("wrote dark_mode.svg, light_mode.svg successfully.")
