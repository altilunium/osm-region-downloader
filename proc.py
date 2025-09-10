import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from datetime import datetime
import sys
sys.stdout.reconfigure(encoding='utf-8')

def analyze_osm_xml(filename):
    tree = ET.parse(filename)
    root = tree.getroot()

    # Prepare storage
    timestamps = []
    contributors = Counter()
    tags_counter = Counter()
    contrib_timestamps = defaultdict(list)

    # Loop through all osm objects
    for elem in root.findall("./*"):
        if elem.tag not in ("node", "way", "relation"):
            continue

        # Collect metadata
        ts = elem.attrib.get("timestamp")
        user = elem.attrib.get("user")

        if ts and user:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            timestamps.append(dt)
            contributors[user] += 1
            contrib_timestamps[user].append(dt)

        # Collect tags
        for tag in elem.findall("tag"):
            k = tag.attrib.get("k")
            if k:
                tags_counter[k] += 1

    # Global oldest/newest
    oldest, newest = min(timestamps), max(timestamps)

    # Top contributors
    top_contribs = contributors.most_common()

    # Most frequent tags
    top_tags = tags_counter.most_common()

    # Contributor lifespans
    lifespan = {}
    for user, tslist in contrib_timestamps.items():
        oldest_user = min(tslist)
        newest_user = max(tslist)
        span = newest_user - oldest_user
        lifespan[user] = span
    lifespan_ranked = sorted(lifespan.items(), key=lambda x: x[1], reverse=True)

    # Print results
    print("=== Global timestamps ===")
    print("Oldest:", oldest)
    print("Newest:", newest)

    print("\n=== Most Frequent Tags ===")
    for tag, count in top_tags:
        print(f"{tag}: {count}")

    print("\n=== Top Contributors (by edits count) ===")
    for user, count in top_contribs:
        print(f"{user}: {count}")


    print("\n=== Contributor Lifespans ===")
    for user, span in lifespan_ranked:
        print(f"{user}: {span}")

if __name__ == "__main__":
    analyze_osm_xml("serang.osm")
