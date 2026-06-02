**Why I Feel the Universe Loves Me**

Product Requirements Document (PRD)

Book Research & Interview Outreach Pipeline

Version 1.0 | May 2026

# **1\. Purpose & Scope**

This document defines the requirements for an automated and semi-automated pipeline to discover, contact, and shortlist interview candidates for the book "Why I Feel the Universe Loves Me" — a collection of real human transformation stories across five core archetypes.

The pipeline must surface 150–200 qualified outreach contacts within 30 days, achieve a 10–15% positive response rate, and produce a shortlist of 10–15 confirmed interview candidates for month two.

## **1.1 Book concept**

- Short, true stories of real people whose lives turned around in ways that made them feel the universe was working for them.

- Pop-culture reference points: Chicken Soup for the Soul, Munnabhai MBBS, Oprah's early show.

- Tone: empathetic, specific, not self-help. Stories are witnessed, not prescribed.

## **1.2 Pre-screen filter**

| The single most important qualifying question Ask every candidate: "What was the moment everything changed for you?" Vivid, specific, sensory answer \= book-ready. Proceed to full interview. Vague, rehearsed, or generic answer \= pass. Do not shortlist regardless of story headline. This question takes 10 minutes and saves hours of unusable interview recordings. |
| :-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |

# **2\. Story Archetypes**

Five primary archetypes define the book's scope. Each archetype has sub-types that represent the full range of transformation stories the pipeline should surface.

## **Archetype 1 — Former extremist / spy / reformed radical**

- **Primary:** Sub-types:
  - Former terrorist or violent extremist who deradicalized

  - Intelligence operative who changed sides or went public

  - Cult member or high-control religion survivor

  - Former gang leader turned community organiser

- What makes the story: the precise moment of ideological break — not the general arc, but the single encounter, conversation, or event that made the worldview collapse.

- Sensitivity level: CRITICAL — always manual outreach via organisational gatekeeper. Never cold contact individuals directly.

## **Archetype 2 — Incarcerated / reformed criminal**

- **Primary:** Sub-types:
  - Formerly incarcerated person who rebuilt a career or business

  - Person who left a life of crime before incarceration

  - White-collar offender turned ethics advocate

  - Juvenile offender with dramatic adult transformation

- What makes the story: what they found inside — a book, a person, a skill — that gave them an identity outside the crime.

- Sensitivity level: HIGH — offer anonymity proactively and prominently in first message.

## **Archetype 3 — Severe health transformation**

- **Primary:** Sub-types:
  - Spontaneous remission or unexpected recovery from terminal/serious diagnosis

  - Mental health crisis survived and transcended

  - Addiction recovery with a second act

  - Disability-to-capability arc (not inspiration porn — genuine reinvention)

- What makes the story: the medicine that worked was not the medicine. The moment they stopped fighting and started listening.

- Key sources: Joe Dispenza community, StoryCorps health tag, YouTube testimony channels.

## **Archetype 4 — Entrepreneurial gig worker**

- **Primary:** Sub-types:
  - Uber/Lyft/DoorDash driver building a parallel business or creative career

  - Gig worker using the flexibility to fund a larger mission

  - Former professional who took gig work deliberately as a reset

- What makes the story: they chose or accepted the downgrade and used it as a launch pad. The car is not the destination.

- Best discovery method: in-person (ride and ask) combined with Reddit subreddit monitoring.

## **Archetype 5 — Blue-collar Covid comeback**

- **Primary:** Sub-types:
  - Factory/trade worker laid off in 2020 who started a business

  - Hospitality/service worker who pivoted to a completely new field

  - Long-term employee who discovered a latent talent during lockdown

  - Immigrant blue-collar worker whose pandemic story involved unusual resilience

- What makes the story: the pandemic removed the identity they thought they needed. The story is what they found when it was gone.

- Key sources: SerpApi local news matrix (8 cities x 6 date windows x 6 queries).

## **Additional story types for any archetype**

- Late bloomer — found calling after 50

- Cycle-breaker — first in family to escape a pattern of poverty, violence, or addiction

- Statistically improbable survival — wrong place, right time

- Caregiver who found meaning through loss

- Public failure and private reconstruction

# **3\. Discovery Sources**

Current execution scope is limited to four active discovery sources:

- SerpApi local news
- YouTube
- Reddit
- ListenNotes

Apify, Apollo, nonprofit/archive scraping, StoryCorps, The Moth, LinkedIn, Instagram, and other sources remain documented as future candidates, but they are paused for now and should not be used in the default pipeline until explicitly reactivated.

The following table maps discovery sources to the story types they surface, the archetypes they cover, the probability of finding a contact email via Hunter.io, the best contact method, and the outreach channel.

| Source                        | Story types                                  | Archetypes | Hunter hit rate | Contact method                                         | Outreach channel        |
| :---------------------------- | :------------------------------------------- | :--------- | :-------------- | :----------------------------------------------------- | :---------------------- |
| YouTube (personal channel)    | Health testimony, recovery, gig driver plans | 3, 4       | 5–10%           | Channel About email (scrape first), then YouTube DM    | Email or platform DM    |
| YouTube TEDx search           | Deradicalization, health, comeback           | 1, 2, 3    | 50–65%          | Hunter.io (name \+ employer domain)                    | Hunter Sequence         |
| Reddit PRAW (live)            | Driver hustle, criminal reform, recovery     | 2, 3, 4    | \<2%            | Reddit DM via PRAW only                                | Reddit DM (manual tone) |
| Reddit Arctic Shift (archive) | Covid layoff, addiction recovery             | 3, 5       | \<2%            | Reddit DM via PRAW                                     | Reddit DM               |
| SerpApi local news            | Covid blue-collar comeback                   | 5          | 35–75%          | Hunter (if business owner) or contact journalist first | Hunter Sequence         |
| Apify — nonprofit pages       | PAUSED — revisit later                       | 1, 2       | 15–25%          | Org comms director — warm intro only                   | Manual email            |
| StoryCorps archive            | Health, loss, survival, all archetypes       | All        | 10–20%          | StoryCorps facilitator or name+city LinkedIn search    | Platform or LinkedIn DM |
| The Moth story archive        | Any first-person arc                         | All        | 40–55%          | Moth speaker bureau or personal site from bio          | Email or speaker bureau |
| TEDx YouTube channel          | Deradicalization, health, comeback           | 1, 3       | 50–65%          | Hunter or TEDx speaker page link                       | Hunter Sequence         |
| ListenNotes (podcast guests)  | All archetypes                               | All        | 50–60%          | Podcast show notes — guest's own links                 | Email or platform DM    |
| Medium / Substack essays      | Recovery, immigrant, comeback                | 2, 3, 5    | 35–50%          | Platform message or author bio link                    | Platform DM             |
| Nonprofit annual reports      | PAUSED — revisit later                       | 1, 2       | 10–20%          | Org comms director — same as nonprofit pages           | Manual email            |
| Apollo.io profiles            | PAUSED — revisit later                       | 5          | 70–80%          | Apollo email built-in (check before Hunter)            | Hunter Sequence         |
| LinkedIn manual search        | Blue-collar, professional pivot              | 5          | 50–60%          | LinkedIn message directly — skip Hunter                | LinkedIn DM (manual)    |
| In-person Uber/Lyft rides     | Entrepreneurial driver                       | 4          | N/A             | Physical card, Airtable manual entry                   | Follow-up email or call |
| SCORE / Chamber spotlights    | Covid comeback, small business               | 5          | 40–60%          | Hunter (business domain) or contact page               | Hunter Sequence         |
| Humans of New York spin-offs  | Any transformation arc                       | All        | 10–20%          | Instagram DM or comment then DM                        | Instagram DM (manual)   |
| University alumni magazines   | Late bloomer, career pivot                   | All        | 45–60%          | Hunter (alumni employer domain)                        | Hunter Sequence         |
| Clean Slate Initiative        | Criminal reform                              | 2          | 10–20%          | Org program director                                   | Manual email            |
| Veterans org newsletters      | Service-to-civilian reinvention              | All        | 40–55%          | Hunter or org contact                                  | Hunter Sequence         |

# **4\. Contact-Finding Logic**

The pipeline applies a waterfall enrichment strategy: each source type has a primary contact method. Hunter.io is used only when a professional domain is likely. For personal/social sources, platform-native channels are superior.

## **4.1 Waterfall by source type**

- YouTube channel: scrape About tab email first → YouTube DM if no email found

- Reddit: Reddit DM only — never attempt Hunter on a pseudonymous username

- Local news article: check article body for business URL → Hunter on business domain → contact the journalist for a warm intro

- Nonprofit page: paused for now; when reactivated, email org comms director → request facilitated introduction to individual

- Podcast show notes: use guest's own linked channels (website, Instagram, LinkedIn) before Hunter

- Apollo / LinkedIn: paused for now; when reactivated, Apollo email built-in → Hunter fallback → LinkedIn InMail

## **4.2 When not to use Hunter**

| Hunter.io is the wrong tool for these sources Reddit usernames — no real name, no domain, Hunter cannot operate YouTube solo creators — no employer domain, hit rate under 10% StoryCorps speakers — private individuals, usually no professional footprint Nonprofit annual report alumni — early-career, no established domain In-person contacts — you already have their details directly |
| :-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |

# **5\. Outreach Methodology**

## **5.1 Universal rules — every archetype**

- First message under 150 words — no exceptions

- Lead with their story, not your project — they need to feel seen before being recruited

- Offer anonymity proactively in the first message — do not wait for them to ask

- One follow-up only — sent 10 days after the initial message, softer in tone

- Never mention book deal, publisher, or commercial context in first contact — lead with human interest

- Always personalise the opening line to something specific about their story

## **5.2 Automated outreach — Hunter Sequences**

The following source types can be handled by Hunter Sequences with archetype-specific templates and personalisation variables:

- TEDx speakers, podcast guests, The Moth performers (professional footprint)

- Apollo/LinkedIn professional profiles are paused for now

- SCORE, Chamber of Commerce, university alumni spotlights

- Local news article subjects who own a business (Hunter email confirmed)

Each Hunter Sequence uses two touches:

- Day 1 — initial outreach (archetype template, personalised opening line variable)

- Day 11 — one follow-up only (shorter, no new pitch, softer tone)

- If positive reply webhook fires, move to Airtable 'Responded' and handle manually from this point

## **5.3 Platform DM outreach — semi-automated**

Reddit DMs via PRAW and Instagram DMs are sent programmatically but require human review of each message before sending. The automation drafts the message; you approve and trigger.

- Reddit: PRAW drafts message referencing the specific post → human reviews → human triggers send

- Instagram: draft prepared by pipeline → human reviews → manual send from your own account

- YouTube DM: comment first (automated, generic interest) → human follows up via channel DM

## **5.4 Handcraft-required outreach**

The following contacts must be written, reviewed, and sent personally. No automation, no templates, no Hunter Sequences.

| ✋ HANDCRAFT REQUIRED — do not automate this outreach Archetype 1 — Former extremist / spy: always handcrafted. Email the organisation (Life After Hate, Moonshot CVE, speaker bureau) not the individual. Your first email is to a gatekeeper — it must explain the book, your credentials, and why this story matters. Expect 1–2 weeks before an intro is facilitated. Archetype 2 — Reformed criminal (via nonprofit): the comms director email is handcrafted. This is a professional letter requesting facilitated access to alumni. Reference the specific alumnus story if you found it in an annual report. Attach a one-page book overview. Local news subjects who are private individuals (not business owners): the journalist email is handcrafted. You are asking a journalist to vouch for you to their source — this requires a personal, thoughtful note. Do not use a template. StoryCorps facilitator contact: handcrafted — reference the specific story URL and explain the book. Any follow-up after a positive reply: once someone expresses interest, all subsequent messages are handcrafted. Automation ends at the first reply. |
| :---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |

| ✋ HANDCRAFT REQUIRED — do not automate this outreach REVIEW GATE — before any batch send in Hunter Sequences: Review a sample of 5 outgoing messages per sequence before activating. Confirm personalisation variables have resolved correctly (no blank {first_name} fields). Confirm the correct archetype template is assigned to each lead. Confirm Hunter-verified emails only — no unverified addresses in the sequence. Sign off manually before each new sequence goes live. |
| :------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |

# **6\. Outreach Templates by Archetype**

All templates below are starting points. Personalisation variables are shown in \[brackets\]. The opening line must always be rewritten to reference something specific about the individual's story before sending.

## **Template A — Health transformation (Hunter Sequence, automated)**

| Subject: Your story — for a book about lives that changed Hi \[first_name\], \[PERSONALISED OPENING — reference specific story detail here\] I'm writing a book called "Why I Feel the Universe Loves Me" — real stories from people who went through something that changed everything, and came out the other side feeling connected to something larger than themselves. I'd love to hear your story in your own words. No agenda beyond listening. Your anonymity is fully protected if you prefer it. Would a 30-minute conversation work for you? |
| :------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |

## **Template B — Covid comeback (Hunter Sequence, automated)**

| Subject: What you built after 2020 — for a book Hi \[first_name\], \[PERSONALISED OPENING — reference article, city, or specific detail\] I'm writing a book about people who lost something in 2020 and found something they couldn't have expected. Not a pandemic book — a resilience book. Real stories, real names or anonymous, entirely your choice. Would you be willing to tell me your story? 30 minutes, no pressure. |
| :------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |

## **Template C — Nonprofit org intro (handcraft, not template)**

| ✋ HANDCRAFT REQUIRED — do not automate this outreach This is not a template — it must be written fresh for each organisation. Address the comms director or program officer by name (find on org website). Reference the specific alumnus story if you found it in their annual report or website. Attach a one-page book overview PDF. Offer to sign any release or NDA the org requires. Tone: peer professional, not supplicant. You are offering their alumni a dignified platform. |
| :--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |

## **Template D — Extremist / former radical (handcraft, always)**

| ✋ HANDCRAFT REQUIRED — do not automate this outreach Never cold-contact an individual in this archetype under any circumstances. First contact is always to the organisation: Life After Hate, Moonshot CVE, speaking bureaus, book agents. Your email to the org must clearly state: book title, your background, why this story matters, how the subject will be protected. Expect a 2–4 week response time. One follow-up after 14 days is appropriate. If the org facilitates an introduction, your first message to the individual is still handcrafted — reference the mutual contact in the opening line. |
| :---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |

# **7\. CRM Status Workflow**

All candidates are tracked in Airtable with the following status progression. Automated transitions are triggered by Hunter webhooks. Manual transitions require human action.

| Status           | Trigger                              | Automated / manual                   | Next action                                                  |
| :--------------- | :----------------------------------- | :----------------------------------- | :----------------------------------------------------------- |
| **New**          | Lead added to Airtable by pipeline   | Automated                            | Review record, confirm score ≥7, approve for outreach        |
| **Contacted**    | Hunter sends initial message         | Automated                            | No action — wait for reply                                   |
| **Followed up**  | Hunter sends day-11 follow-up        | Automated                            | No action — wait for reply                                   |
| **Responded**    | Positive reply webhook fires         | Automated detection, manual handling | YOU take over — handcraft all replies from here              |
| **Pre-screened** | 10-min call completed                | Manual                               | Log answer to the turning-point question. Pass or shortlist. |
| **Shortlisted**  | Pre-screen passed                    | Manual                               | Send consent form, book interview slot for month 2           |
| **Declined**     | No reply after follow-up, or soft no | Manual or automated                  | Archive — do not contact again                               |
| **Bounced**      | Hunter email not deliverable         | Automated                            | Try alternative contact method, update record                |

# **8\. Month-1 Sprint Plan**

## **Week 1 — launch all five pipelines simultaneously**

- Run SerpApi full matrix (288 searches or 90 reduced) — blue-collar archetype

- Run YouTube keyword searches for health \+ driver archetypes

- Start Reddit PRAW monitoring for all relevant subreddits

- Apify scrape of nonprofit speaker pages — paused; revisit later

- Apollo.io export for professional pivot profiles — paused; revisit later

- All raw leads scored by Claude API, deduplicated, loaded into Airtable

- First Hunter Sequences launched for fast archetypes (health, driver, blue-collar)

- Handcrafted emails sent to Life After Hate, Defy Ventures, SCORE comms contacts

## **Week 2 — enrich and first follow-up wave**

- Hunter enrichment run on all week-1 leads with professional footprint

- Platform DMs drafted and reviewed for Reddit and YouTube leads

- First replies begin arriving — handle all manually from first reply

- Review Hunter open rates — adjust subject lines if below 30%

## **Week 3 — pre-screen calls**

- Target 20–30 pre-screen calls (10 minutes each)

- Ask the turning-point question — log responses verbatim in Airtable

- Shortlist decisions made — aim for 10–15 confirmed by end of week

- Day-11 follow-ups sent by Hunter automatically

## **Week 4 — lock the interview calendar**

- Send consent forms to all shortlisted candidates

- Book interview slots for month 2 — confirm dates, send calendar invites

- Buffer: expect 2–3 cancellations — keep 2 reserves on warm standby

- Archive all non-respondents in Airtable

## **Month-1 targets**

| Metric                            | Target         |
| :-------------------------------- | :------------- |
| Total outreach contacts           | **150–200**    |
| Positive response rate            | **10–15%**     |
| Pre-screen calls completed        | **20–30**      |
| Shortlisted interview candidates  | **10–15**      |
| Confirmed month-2 interview slots | **10 minimum** |
| Total month-1 cost                | **\~$101**     |
