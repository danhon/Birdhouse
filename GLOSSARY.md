# Glossary

The words this project uses, so "public", "user" and "history" do not drift
between places.

**Operator** — the person who installs and runs Birdhouse next to their own
BirdNET-Go installation. The person the installation docs address.

**Viewer** — a person looking at the display or page. A viewer has no account
and does nothing but look, tap a slide, and open a panel.

**Maintainer** — the person who answers issues and cuts releases. Today,
Dan.

**BirdNET-Go instance** — a running BirdNET-Go whose detections Birdhouse
presents. One Birdhouse serves one instance.

**Reference instance** — Dan's ubuntuplex deployment. It is the behaviour
every change must preserve: public, no authentication, one wall.

**Detection** — one event BirdNET-Go recorded above the confidence floor. The
same event can be described by more than one model; Birdhouse merges those
into one species entry.

**Species today** — a bird with at least one detection on the current local
day. It appears on exactly one slide.

**History** — the last 30 local days for one species, including the days it
was not detected.

**Layout** — one of the two readings of a history: **Bars** (a bar per day
against a detection axis) or **Calendar** (a month grid whose squares carry
each day's count).

**Public** — the repository and its distribution to other operators. It does
not mean a service Dan runs for them; Birdhouse is self-hosted.
