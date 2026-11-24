"""Render the profile's contribution statistics and self-contained portrait panels."""
import base64
import json
import os
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from xml.sax.saxutils import escape

root = Path(__file__).resolve().parents[1]
assets = root / "assets"
owner = os.environ["GITHUB_REPOSITORY_OWNER"]
today = datetime.now(timezone.utc).date()

def graphql(query, **variables):
    payload = json.dumps({"query": query, "variables": variables}).encode("utf-8")
    request = Request("https://api.github.com/graphql", data=payload, headers={
        "Authorization": "Bearer " + os.environ["GITHUB_TOKEN"],
        "Content-Type": "application/json", "User-Agent": "github-profile-update"
    })
    with urlopen(request, timeout=45) as response:
        result = json.load(response)
    if result.get("errors"):
        raise RuntimeError("; ".join(error["message"] for error in result["errors"]))
    return result["data"]

def fetch_metrics():
    query = """query($login:String!, $after:String) {
      user(login:$login) { createdAt avatarUrl(size:420)
        pullRequests {totalCount} issues {totalCount}
        contributionsCollection {totalCommitContributions totalRepositoriesWithContributedCommits}
        repositories(first:100,after:$after,privacy:PUBLIC,isFork:false,ownerAffiliations:OWNER) {
          pageInfo {hasNextPage endCursor} nodes {stargazerCount languages(first:100) {
            edges {size node {name color}} } } } } }"""
    after, stars, languages = None, 0, {}
    while True:
        user = graphql(query, login=owner, after=after)["user"]
        repos = user["repositories"]
        for repo in repos["nodes"]:
            stars += repo["stargazerCount"]
            for edge in repo["languages"]["edges"]:
                name, color = edge["node"]["name"], edge["node"]["color"]
                prev = languages.get(name, (0, color))[0]
                languages[name] = (prev + edge["size"], color or "#8892a6")
        if not repos["pageInfo"]["hasNextPage"]:
            break
        after = repos["pageInfo"]["endCursor"]
    days = {}
    calendar_query = """query($login:String!, $start:DateTime!, $end:DateTime!) {
      user(login:$login){contributionsCollection(from:$start,to:$end) {
        contributionCalendar {weeks {contributionDays {date contributionCount}}} } } }"""
    for year in range(int(user["createdAt"][:4]), today.year + 1):
        end = min(date(year,12,31),today)
        data = graphql(calendar_query, login=owner, start=f"{year}-01-01T00:00:00Z",
                       end=f"{end.isoformat()}T23:59:59Z")
        weeks = data["user"]["contributionsCollection"]["contributionCalendar"]["weeks"]
        for week in weeks:
            for day in week["contributionDays"]:
                when = date.fromisoformat(day["date"])
                if when.year == year and when <= today:
                    days[when] = day["contributionCount"]
    return user, stars, languages, days

def text(x,y,value,size=18,color="#e5e7eb",align="start",weight=550):
    return f'<text x="{x}" y="{y}" text-anchor="{align}" fill="{color}" font-size="{size}" font-weight="{weight}">{escape(str(value))}</text>'

def draw_stats(user,stars,languages,days):
    cyan, pink = "#22d3ee", "#f43f5e"
    svg = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 425" font-family="Arial,Helvetica,sans-serif"><title>GitHub statistics, languages and contribution streaks for Mohd Nadeem</title><rect width="1000" height="425" rx="15" fill="#0d1117"/>']
    svg.append(text(42,52,"Mohd Nadeem’s GitHub Stats",23,cyan))
    activity = user["contributionsCollection"]
    rows = [("Stars earned",stars),("Commits · past year",activity["totalCommitContributions"]),
            ("Pull requests",user["pullRequests"]["totalCount"]),("Issues",user["issues"]["totalCount"]),
            ("Repos committed to · past year",activity["totalRepositoriesWithContributedCommits"])]
    for i,(label,num) in enumerate(rows):
        y = 91 + i*27
        svg.extend([text(42,y,["★","◷","⑂","◎","▤"][i],20,pink),text(70,y,label,16),text(359,y,num,17)])
    svg.append(text(494,68,"Most Used Languages",25,cyan))
    langs = sorted(languages.items(),key=lambda x:-x[1][0])
    total = sum(item[1][0] for item in langs)
    x = 496
    for name,(size,color) in langs:
        width = 453 * size / total
        svg.append(f'<rect x="{x:.2f}" y="96" width="{width:.2f}" height="11" fill="{color}"/>')
        x += width
    for i,(name,(size,color)) in enumerate(langs[:6]):
        x, y = 504+(i%2)*225, 139+(i//2)*25
        svg.extend([f'<circle cx="{x}" cy="{y-5}" r="6" fill="{color}"/>',text(x+13,y,f"{name} {100*size/total:.1f}%",15)])
    active = sorted(d for d,count in days.items() if count)
    longest, run, previous = 0, 0, None
    for day in active:
        run = run+1 if previous and (day-previous).days == 1 else 1
        longest = max(run,longest)
        previous = day
    current = run if previous and (today-previous).days <= 1 else 0
    svg.append('<path d="M331 267v125 M668 267v125" stroke="#8494a6"/><circle cx="500" cy="303" r="41" fill="none" stroke="#22d3ee" stroke-width="6"/>')
    for x,num,label in [(170,sum(days.values()),"Total contributions"),(500,current,"Current streak"),(830,longest,"Longest streak")]:
        svg.extend([text(x,315,num,36,"#f0f4fa","middle",700),text(x,375,label,20,cyan if x==500 else "#e5e7eb","middle")])
    svg.append(text(500,409,f"Public GitHub activity · Updated {today.isoformat()} UTC",13,"#99a6b6","middle"))
    return "".join(svg)+"</svg>"

def update_portraits(avatar_url):
    portraits = {}
    for role in ("front","pointing"):
        path = next((assets / f"portrait-{role}.{ext}" for ext in ("png","jpg","jpeg","webp") if (assets / f"portrait-{role}.{ext}").is_file()),None)
        if path:
            mime = {"jpg":"jpeg","jpeg":"jpeg","png":"png","webp":"webp"}[path.suffix[1:]]
            portraits[role] = "data:image/"+mime+";base64,"+base64.b64encode(path.read_bytes()).decode()
    if "front" not in portraits:
        with urlopen(Request(avatar_url,headers={"User-Agent":"github-profile-update"}),timeout=25) as response:
            mime = response.headers.get_content_type()
            if mime not in ("image/png","image/jpeg","image/webp","image/gif"):
                raise ValueError("Unsupported avatar format")
            portraits["front"] = "data:"+mime+";base64,"+base64.b64encode(response.read()).decode()
    portraits.setdefault("pointing",portraits["front"])
    for filename,role in [("hero.svg","front"),("record.svg","front"),("connect.svg","pointing")]:
        path = assets / filename
        svg = path.read_text(encoding="utf-8")
        pattern = r'(<image data-portrait="[^"]+"[^>]*? )href="[^"]*"'
        svg, count = re.subn(pattern,lambda m:m.group(1)+'href="'+portraits[role]+'"',svg)
        if count != 1:
            raise ValueError("Expected a single portrait in " + filename)
        path.write_text(svg,encoding="utf-8")

if __name__ == "__main__":
    user,stars,languages,days = fetch_metrics()
    (assets/"analytics.svg").write_text(draw_stats(user,stars,languages,days),encoding="utf-8")
    update_portraits(user["avatarUrl"])
