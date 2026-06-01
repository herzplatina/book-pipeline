

**Why I Feel the Universe Loves Me**

Engineering Design Document (EDD)

Lead Discovery, Scoring, Enrichment & Outreach Pipeline

Version 1.0  |  May 2026

# **1\. System Overview**

This document defines the technical architecture, data flow, API integrations, and variable schemas for the five-stage lead generation pipeline. It is written for use with Claude Code and covers every module from raw discovery to Airtable CRM entry and Instantly.ai outreach dispatch.

## **1.1  Five-stage pipeline summary**

* Stage 1 — Discover: five modules (YouTube, Reddit, SerpApi news, nonprofits/archives, professional) each produce a raw leads list as JSON

* Stage 2 — Score: Claude API Haiku 4.5 reads each raw lead, returns score (1–10), extracted name, archetype match, one-sentence summary

* Stage 3 — Enrich: Hunter.io finds and verifies email for leads with professional footprint; platform channels used for others

* Stage 4 — Outreach: Instantly.ai sequences for automated archetypes; PRAW / manual for sensitive archetypes

* Stage 5 — CRM: Airtable stores all leads with full field schema; Instantly webhooks update status automatically

## **1.2  Repository structure**

| book-pipeline/   config/     settings.py          \# all API keys, thresholds, city/query matrices   modules/     m1\_youtube.py        \# YouTube Data API v3 \+ transcript fetch \+ About scrape     m2\_reddit.py         \# PRAW live \+ Arctic Shift archive \+ DM sender     m3\_serpapi.py        \# SerpApi matrix \+ article fetch \+ dedup     m4\_nonprofits.py     \# Apify scraper \+ StoryCorps \+ Moth \+ ListenNotes     m5\_professional.py   \# Apollo.io \+ LinkedIn manual queue   scoring/     claude\_scorer.py     \# Claude API Haiku scoring engine     prompts.py           \# scoring prompt templates per archetype   enrichment/     hunter.py            \# email find \+ verify waterfall     contact\_router.py    \# decides Hunter vs platform DM vs org intro   outreach/     instantly.py         \# Instantly API v2 lead add \+ campaign management     praw\_dm.py           \# Reddit DM draft \+ human-review queue     manual\_queue.py      \# Airtable queue for handcraft-required contacts   crm/     airtable.py          \# Airtable API read/write, status transitions     schema.py            \# field definitions and validation   pipeline.py            \# master orchestrator — runs all stages in order   requirements.txt |
| :---- |

# **2\. Complete API & Tool Reference**

All tools used across all five modules, with authentication method, cost, and key variables.

| Tool / API | Module | Cost | Auth method | Key variables / endpoints |
| :---- | :---- | :---- | :---- | :---- |
| YouTube Data API v3 | M1 | Free | API key (GCP) | q, type=video, maxResults, videoDuration, channelId |
| youtube-transcript-api | M1 | Free | None required | YouTubeTranscriptApi.get\_transcript(video\_id) |
| requests \+ BeautifulSoup | M1, M4 | Free | None | GET channel About URL, parse .yt-channel-external-link |
| Reddit PRAW | M2 | Free | OAuth2 (client\_id, client\_secret, user\_agent) | subreddit.search(query, limit, time\_filter), redditor.message() |
| Arctic Shift API | M2 | Free | None | GET /api/posts?q=\&subreddit=\&after=\&before= |
| SerpApi (Google engine) | M3 | Free / $50 Basic | api\_key param | engine=google, q, location, gl, hl, as\_qdr=custom, tbs=cdr:1,cd\_min:,cd\_max:, num |
| newspaper3k | M3 | Free | None | Article(url).download().parse() → .text, .authors |
| Apify web scraper | M4 | Free tier | APIFY\_TOKEN env var | actor run: url list, page function JS |
| ListenNotes API | M4 | Free (10/mo) | X-ListenAPI-Key header | GET /api/v2/search?q=\&type=episode\&language=English |
| Apollo.io API | M5 | Free (50 exports) | api\_key in JSON body | POST /v1/mixed\_people/search — filters: employment\_history, industry |
| Claude API (Haiku 4.5) | Scoring | \~$5/mo | x-api-key header (Anthropic) | model, max\_tokens, messages, system prompt with archetype schema |
| Hunter.io Email Finder | Enrichment | $49/mo Starter | api\_key param | GET /email-finder?domain=\&first\_name=\&last\_name= |
| Hunter.io Verifier | Enrichment | Included | api\_key param | GET /email-verifier?email= |
| Instantly API v2 | Outreach | $47/mo Growth | Authorization: Bearer token | POST /api/v1/lead/add, POST /api/v1/campaign/activate |
| Airtable API | CRM | Free | Authorization: Bearer PAT | POST/PATCH /v0/{baseId}/{tableId} — records array with fields object |
| Make.com (optional) | Orchestration | $9/mo Core | Webhook triggers | HTTP module, Airtable module, Instantly module |

# **3\. Stage 1 — Discovery Modules**

## **Module 1 — YouTube discovery**

### **Variable schema**

| YOUTUBE\_SEARCH\_QUERIES \= {     'health':  \['Joe Dispenza healing miracle', 'spontaneous remission story',                 'healed from cancer story', 'mental health recovery transformation'\],     'driver':  \['Uber driver entrepreneur story', 'gig worker building business',                 'driving for Uber while building startup'\],     'criminal':\['life after prison success', 'reformed criminal entrepreneur',                 'formerly incarcerated second chance story'\] } YOUTUBE\_FILTERS \= {     'videoDuration': 'medium',   \# 4–20 min — personal testimonials, not lectures     'type': 'video',     'maxResults': 50,     'order': 'relevance' } |
| :---- |

### **Data flow**

| \# | Step name | Input | Process | Output |
| :---- | :---- | :---- | :---- | :---- |
| **1** | **YouTube search** | query string per archetype | YouTube Data API v3 search.list() | list of {video\_id, title, channel\_id, description} |
| **2** | **Transcript fetch** | video\_id | youtube-transcript-api.get\_transcript() | raw transcript text string |
| **3** | **About page scrape** | channel\_id | requests GET youtube.com/channel/{id}/about | contact\_email or None |
| **4** | **Score** | transcript text | Claude API scorer (see Stage 2\) | score, name, archetype\_match, summary |
| **5** | **Route contact** | score ≥ 7 | contact\_router: About email → YouTube DM draft | contact\_method, contact\_value |

## **Module 2 — Reddit discovery**

### **Variable schema**

| SUBREDDITS \= {     'driver':   \['UberDrivers', 'lyftdrivers', 'gig\_economy'\],     'criminal': \['offmychest', 'reentry', 'excons'\],     'health':   \['addiction', 'Recovery', 'CPTSD', 'offmychest'\],     'bluecollar': \['AskWorkplace', 'jobs', 'careerguidance'\] } REDDIT\_KEYWORDS \= \[     'started a business', 'entrepreneur', 'built something',     'second chance', 'turned my life around', 'got out and',     'healed from', 'sober and now', 'lost my job and' \] REDDIT\_FILTERS \= {     'min\_score': 100,          \# upvotes — proxy for story quality     'time\_filter': 'year',     'limit': 100 } ARCTIC\_SHIFT\_DATE\_RANGE \= {     'after': '2020-01-01',     'before': '2023-12-31' } |
| :---- |

### **Data flow**

| \# | Step name | Input | Process | Output |
| :---- | :---- | :---- | :---- | :---- |
| **1** | **Live subreddit scan** | subreddit name \+ keyword | praw.subreddit().search() | list of {post\_id, author, title, selftext, score, url} |
| **2** | **Archive scan** | subreddit \+ date range | Arctic Shift API GET /api/posts | historical posts 2020–2023 |
| **3** | **Score post** | selftext | Claude API scorer | score, name\_if\_revealed, archetype\_match |
| **4** | **Draft DM** | score ≥ 7, post\_id | praw\_dm.py draft\_message(post\_id) | draft message string — ENTERS HUMAN REVIEW QUEUE |
| **5** | **Human approves** | draft message | Manual review — human triggers send | PRAW redditor.message() called |

| ✋  HANDCRAFT REQUIRED All Reddit DMs enter a human review queue before sending — never auto-send. Reference the specific post in the opening line of every DM. Maximum 10 DMs per day per Reddit account to avoid spam flags. Do not attempt Hunter.io on Reddit usernames — no domain, hit rate \<2%. |
| :---- |

## **Module 3 — SerpApi local news (blue-collar archetype)**

### **Variable schema**

| CITIES \= \[     ('Detroit, Michigan, United States',        \['detroitnews.com','freep.com','mlive.com'\]),     ('Pittsburgh, Pennsylvania, United States', \['post-gazette.com','wesa.fm','triblive.com'\]),     ('Cleveland, Ohio, United States',          \['cleveland.com','crainscleveland.com','ideastream.org'\]),     ('Tulsa, Oklahoma, United States',          \['tulsaworld.com','tulsapeople.com','kjrh.com'\]),     ('Louisville, Kentucky, United States',     \['courier-journal.com','wdrb.com','louisvillemag.com'\]),     ('Memphis, Tennessee, United States',       \['commercialappeal.com','dailymemphian.com','wreg.com'\]),     ('Fresno, California, United States',       \['fresnobee.com','kvpr.org','abc30.com'\]),     ('El Paso, Texas, United States',           \['elpasotimes.com','kvia.com','elpasomatters.org'\]) \] DATE\_WINDOWS \= \[     ('1/1/2020', '6/30/2020',  'early\_covid'),     ('7/1/2020', '12/31/2020', 'late\_covid'),     ('1/1/2021', '6/30/2021',  'rebuild\_early'),   \# PRIORITY     ('7/1/2021', '12/31/2021', 'rebuild\_peak'),    \# PRIORITY     ('1/1/2022', '12/31/2022', 'established'),     ('1/1/2023', '12/31/2023', 'lookback') \] QUERY\_TERMS \= \[     '"lost job" "Covid" "started"',     '"laid off" "pandemic" "built"',     '"Covid" "layoff" "comeback"',     '"lost everything" "Covid" "now"',     '"pandemic" "unemployed" "entrepreneur"',     '"furloughed" "Covid" "new business"' \] SERPAPI\_PARAMS\_TEMPLATE \= {     'engine': 'google',     'gl': 'us', 'hl': 'en',     'as\_qdr': 'custom',     'num': 10,     'api\_key': SERPAPI\_KEY     \# tbs, q, location injected per matrix cell } |
| :---- |

### **Data flow**

| \# | Step name | Input | Process | Output |
| :---- | :---- | :---- | :---- | :---- |
| **1** | **Build matrix** | CITIES × DATE\_WINDOWS × QUERY\_TERMS | itertools.product() — 288 combos full / 90 reduced | list of (city, sites, cd\_min, cd\_max, window, query) |
| **2** | **SerpApi call** | one matrix cell | requests.get serpapi.com/search — q \= query \+ site:A OR site:B | {organic\_results: \[{title, link, snippet, date, source}\]} |
| **3** | **Deduplicate** | all results so far | seen\_urls set — skip if url already processed | unique article list |
| **4** | **Fetch article** | article URL | newspaper3k Article(url).parse() | full text, authors list |
| **5** | **Claude extract** | article full text | Claude API: extract named individual \+ score story fit | name, score, summary, archetype\_match |
| **6** | **Contact route** | name, article source domain | if business\_owner: Hunter domain search; else: journalist email | email or journalist\_contact |

| Rate limiting Sleep 1.2 seconds between SerpApi calls to stay within rate limits. Full matrix (288 calls) requires SerpApi Basic plan at $50/mo. Reduced matrix (5 cities × 6 windows × 3 queries \= 90 calls) fits within free tier. |
| :---- |

## **Module 4 — Nonprofits, archives & media**

### **Key sources and scraping targets**

| NONPROFIT\_URLS \= \[     'https://defyventures.org/alumni-stories/',     'https://www.prisonfellowship.org/stories/',     'https://thedoefund.org/stories/',     'https://lifeafterhate.org/our-team/',    \# speakers only     'https://moonshotcve.com/people/',     'https://cleanslate.org/stories/' \] STORYCORPS\_SEARCH\_TAGS \= \['health', 'recovery', 'resilience', 'second chance', 'immigration'\] MOTH\_SEARCH\_TAGS \= \['transformation', 'identity', 'illness', 'crime', 'immigration'\] LISTENNOTES\_QUERIES \= \[     'former prisoner entrepreneur',     'Joe Dispenza healing story',     'Covid job loss rebuilt life',     'deradicalization story',     'addiction recovery second career' \] |
| :---- |

### **Data flow**

| \# | Step name | Input | Process | Output |
| :---- | :---- | :---- | :---- | :---- |
| **1** | **Apify scrape** | URL list from NONPROFIT\_URLS | Apify actor run with page function | {name, bio\_text, role, page\_url} per person |
| **2** | **StoryCorps search** | tag list | requests GET storycorps.org/stories/?tag= | {name, city, story\_url, description} |
| **3** | **Moth search** | tag list | requests GET themoth.org/stories?tag= | {name, bio\_link, story\_title} |
| **4** | **ListenNotes search** | query list | GET /api/v2/search?q=\&type=episode | {podcast\_name, episode\_title, description, pub\_date} |
| **5** | **Score all** | bio or description text | Claude API scorer per record | score, archetype\_match, summary |
| **6** | **Org queue** | nonprofit alumni (score ≥ 7\) | manual\_queue.py — add to Airtable 'Manual Outreach' queue | Airtable record with status=NeedsHandcraft |

| ✋  HANDCRAFT REQUIRED Nonprofit alumni and Life After Hate contacts MUST go to manual\_queue — never Instantly. The org comms director email is the first handcrafted message, not contact to the individual. Do not attempt Hunter.io for StoryCorps or annual report subjects — hit rate under 15%. |
| :---- |

## **Module 5 — Professional discovery**

### **Apollo.io search filter schema**

| APOLLO\_SEARCH\_PAYLOAD \= {     'api\_key': APOLLO\_KEY,     'q\_organization\_industry\_tag\_ids': \[        \# blue-collar industries         'manufacturing', 'construction', 'transportation',         'hospitality', 'retail', 'food\_and\_beverage'     \],     'employment\_history': {         'end\_date\_range': {'min': '2020-01-01', 'max': '2021-06-30'},  \# job ended during Covid         'current': False     },     'q\_keywords': 'founder OR owner OR started OR built OR launched',     'page': 1, 'per\_page': 50 } |
| :---- |

| \# | Step name | Input | Process | Output |
| :---- | :---- | :---- | :---- | :---- |
| **1** | **Apollo search** | filter payload above | POST /v1/mixed\_people/search | list of {first\_name, last\_name, title, company, email, linkedin\_url} |
| **2** | **Email check** | Apollo response | if email present in Apollo: use it; else: Hunter fallback | verified\_email or None |
| **3** | **Score profile** | title \+ company description | Claude API: does employment gap suggest Covid pivot story? | score, story\_hypothesis |
| **4** | **LinkedIn queue** | profiles with no email found | manual\_queue.py LinkedIn tab — for manual connection request | Airtable record with channel=LinkedIn |

# **4\. Stage 2 — Claude API Scoring Engine**

## **4.1  Scoring prompt template**

| SYSTEM\_PROMPT \= '''You are a story evaluator for a book about human transformation. You will receive a piece of text (transcript, Reddit post, or article excerpt). Return ONLY a JSON object with these exact fields: {   "score": \<integer 1-10\>,   "name": \<string or null — extracted full name if mentioned\>,   "archetype": \<one of: extremist, criminal, health, driver, bluecollar, other\>,   "archetype\_match": \<true or false\>,   "turning\_point": \<string — one sentence describing the specific moment of change, or null\>,   "summary": \<string — one sentence describing the story\>,   "contact\_clue": \<string or null — any email, website, social handle mentioned\> } Score 8-10: vivid, specific turning point, named individual, emotionally resonant. Score 5-7: clear transformation arc but vague on the turning point moment. Score 1-4: generic, no named individual, no specific transformation event. Return ONLY the JSON object. No preamble, no explanation.''' def score\_content(text, archetype\_hint=None):     user\_msg \= f'Archetype hint: {archetype\_hint}\\n\\nContent:\\n{text\[:4000\]}'     response \= anthropic\_client.messages.create(         model='claude-haiku-4-5-20251001',         max\_tokens=300,         system=SYSTEM\_PROMPT,         messages=\[{'role': 'user', 'content': user\_msg}\]     )     return json.loads(response.content\[0\].text) |
| :---- |

## **4.2  Scoring thresholds**

* Score ≥ 8: Auto-approve for enrichment and outreach pipeline

* Score 6–7: Add to Airtable with status=NeedsReview — human decides

* Score ≤ 5: Discard — do not enrich or contact

* archetype\_match \= false: Flag for manual review regardless of score

# **5\. Stage 3 — Enrichment & Contact Routing**

## **5.1  Contact router logic**

| def route\_contact(lead: dict) \-\> dict:     source \= lead\['source'\]          \# Sources where Hunter is unlikely to work     if source in \['reddit', 'youtube\_personal', 'storycorps', 'nonprofit\_annual\_report'\]:         return platform\_channel(lead)   \# Reddit DM, YouTube DM, org intro          \# Sources where Hunter works well     if source in \['apollo', 'tedx', 'moth', 'podcast\_guest', 'news\_business\_owner'\]:         email \= hunter\_find(lead\['name'\], lead\['employer\_domain'\])         if email and email\['confidence'\] \>= 70:             verified \= hunter\_verify(email\['value'\])             if verified\['result'\] \== 'deliverable':                 return {'method': 'email', 'value': email\['value'\], 'channel': 'instantly'}          \# Sensitive archetypes — always manual regardless of email availability     if lead\['archetype'\] in \['extremist', 'criminal'\] and lead\['source'\] \== 'nonprofit':         return {'method': 'org\_intro', 'value': lead\['org\_comms\_email'\],                 'channel': 'manual', 'requires\_handcraft': True}          \# Fallback: platform channel     return platform\_channel(lead) |
| :---- |

## **5.2  Hunter API call pattern**

| import requests def hunter\_find(first\_name, last\_name, domain):     resp \= requests.get('https://api.hunter.io/v2/email-finder', params={         'domain': domain,         'first\_name': first\_name,         'last\_name': last\_name,         'api\_key': HUNTER\_KEY     })     data \= resp.json()\['data'\]     return data if data.get('confidence', 0\) \>= 70 else None def hunter\_verify(email):     resp \= requests.get('https://api.hunter.io/v2/email-verifier', params={         'email': email, 'api\_key': HUNTER\_KEY     })     return resp.json()\['data'\]  \# result: 'deliverable' | 'risky' | 'undeliverable' |
| :---- |

# **6\. Stage 4 — Outreach**

## **6.1  Instantly.ai lead add and campaign assignment**

| INSTANTLY\_CAMPAIGNS \= {     'health':     'campaign\_id\_health\_transformation',     'driver':     'campaign\_id\_entrepreneurial\_driver',     'bluecollar': 'campaign\_id\_covid\_comeback',     'tedx':       'campaign\_id\_tedx\_speakers',     'podcast':    'campaign\_id\_podcast\_guests' } def add\_to\_instantly(lead: dict):     payload \= {         'email': lead\['verified\_email'\],         'first\_name': lead\['first\_name'\],         'personalization': lead\['opening\_line'\],   \# SET THIS — never leave blank         'campaign\_id': INSTANTLY\_CAMPAIGNS\[lead\['archetype'\]\],         'custom\_variables': {             'story\_source': lead\['source'\],             'story\_summary': lead\['claude\_summary'\],             'city': lead.get('city', ''),             'archetype': lead\['archetype'\]         }     }     resp \= requests.post('https://api.instantly.ai/api/v1/lead/add',         headers={'Authorization': f'Bearer {INSTANTLY\_KEY}'},         json=payload)     return resp.json() |
| :---- |

## **6.2  Handcraft-required outreach — manual queue**

| ✋  HANDCRAFT REQUIRED The following lead types are NEVER sent to Instantly. They enter manual\_queue in Airtable:   1\. archetype \= 'extremist' — ALL contacts, every source   2\. archetype \= 'criminal' AND source \= 'nonprofit' or 'org\_intro'   3\. source \= 'local\_news' AND contact\_method \= 'journalist\_intro'   4\. source \= 'storycorps' or 'annual\_report'   5\. status \= 'Responded' — any archetype, any source For items 1–4: write a fresh personalised email. Do not use templates. For item 5: automation ends at first reply. Every subsequent message is handcrafted. Review gate: inspect 5 sample Instantly messages before activating any new campaign. |
| :---- |

## **6.3  Reddit DM review queue**

| def queue\_reddit\_dm(lead: dict):     '''Adds drafted DM to Airtable manual review queue — does NOT send.'''     draft \= generate\_reddit\_dm\_draft(         username=lead\['reddit\_username'\],         post\_title=lead\['post\_title'\],         post\_snippet=lead\['post\_text'\]\[:200\],         archetype=lead\['archetype'\]     )     airtable.create\_record('Manual DM Queue', {         'Username': lead\['reddit\_username'\],         'Post URL': lead\['post\_url'\],         'Draft Message': draft,         'Status': 'Awaiting Review',         'Channel': 'Reddit DM'     })     \# Human opens Airtable, reviews draft, edits if needed,     \# changes Status to 'Approved', then triggers send\_approved\_dms() |
| :---- |

# **7\. Stage 5 — Airtable CRM Schema**

## **7.1  Contacts table fields**

| CONTACTS\_FIELDS \= {     'Name':             str,    \# extracted by Claude or from source     'First Name':       str,     'Last Name':        str,     'Archetype':        enum,   \# extremist|criminal|health|driver|bluecollar     'Source':           str,    \# youtube|reddit|serpapi|nonprofit|apollo|...     'Source URL':       str,    \# link to original video/post/article     'City':             str,     'Date Window':      str,    \# SerpApi window label e.g. rebuild\_peak     'Claude Score':     int,    \# 1–10     'Story Summary':    str,    \# one sentence from Claude     'Turning Point':    str,    \# extracted by Claude if present     'Email':            str,    \# verified by Hunter     'Email Confidence': int,    \# Hunter confidence score 0–100     'Contact Method':   enum,   \# email|reddit\_dm|instagram\_dm|org\_intro|linkedin     'Contact Value':    str,    \# the actual email/handle/URL     'Requires Handcraft': bool, \# True for extremist, criminal-org, journalist-intro     'Status':           enum,   \# New|Contacted|Responded|Pre-screened|Shortlisted|Declined|Bounced     'Instantly Lead ID':str,    \# returned by Instantly API on lead add     'Replied':          bool,   \# set by Instantly webhook     'Reply Sentiment':  enum,   \# positive|neutral|unsubscribe|bounce     'Pre-screen Notes': str,    \# your notes from the 10-min call     'Turning Point Answer': str,\# their verbatim answer to the key question     'Shortlisted':      bool,     'Interview Date':   date,     'Consent Received': bool,     'Created At':       datetime } |
| :---- |

## **7.2  Instantly webhook handler**

| from flask import Flask, request app \= Flask(\_\_name\_\_) @app.route('/webhook/instantly', methods=\['POST'\]) def instantly\_webhook():     event \= request.json     lead\_email \= event\['email'\]     sentiment \= event\['reply\_category'\]  \# positive|neutral|unsubscribe|bounce          record \= airtable.find\_by\_email(lead\_email)     if not record: return '', 200          if sentiment \== 'positive':         airtable.update(record\['id'\], {             'Status': 'Responded',             'Replied': True,             'Reply Sentiment': 'positive'         })         \# Send Slack/email notification to YOU — take over manually         notify\_owner(f'Positive reply from {lead\_email} — take over now')     elif sentiment \== 'bounce':         airtable.update(record\['id'\], {'Status': 'Bounced', 'Replied': False})     else:         airtable.update(record\['id'\], {'Replied': True, 'Reply Sentiment': sentiment})          return '', 200 |
| :---- |

# **8\. Master Pipeline Orchestrator**

| \# pipeline.py — run this to execute all stages in sequence def run\_pipeline():     all\_raw\_leads \= \[\]     \# Stage 1 — Discovery     print('\[1/5\] Running discovery modules...')     all\_raw\_leads \+= m1\_youtube.discover()     all\_raw\_leads \+= m2\_reddit.discover()     all\_raw\_leads \+= m3\_serpapi.discover()      \# sleeps 1.2s between calls     all\_raw\_leads \+= m4\_nonprofits.discover()     all\_raw\_leads \+= m5\_professional.discover()     print(f'  Raw leads collected: {len(all\_raw\_leads)}')     \# Stage 2 — Score     print('\[2/5\] Scoring with Claude API...')     scored \= \[claude\_scorer.score(lead) for lead in all\_raw\_leads\]     qualified \= \[l for l in scored if l\['score'\] \>= 7\]     print(f'  Qualified leads (score \>= 7): {len(qualified)}')     \# Stage 3 — Enrich     print('\[3/5\] Enriching contacts...')     enriched \= \[contact\_router.route(lead) for lead in qualified\]     \# Stage 4 — Outreach     print('\[4/5\] Dispatching outreach...')     for lead in enriched:         if lead\['requires\_handcraft'\]:             manual\_queue.add(lead)           \# human handles         elif lead\['channel'\] \== 'instantly':             instantly.add\_lead(lead)         \# automated sequence         elif lead\['channel'\] \== 'reddit\_dm':             praw\_dm.queue\_for\_review(lead)   \# human reviews then sends     \# Stage 5 — CRM     print('\[5/5\] Writing to Airtable...')     for lead in enriched:         airtable.upsert(lead)                \# dedup by Source URL     print(f'Pipeline complete. {len(enriched)} leads in Airtable.') if \_\_name\_\_ \== '\_\_main\_\_':     run\_pipeline() |
| :---- |

# **9\. Environment & Configuration**

## **9.1  Required environment variables**

| \# config/settings.py — load from .env, never commit to repo import os YOUTUBE\_API\_KEY     \= os.environ\['YOUTUBE\_API\_KEY'\] REDDIT\_CLIENT\_ID    \= os.environ\['REDDIT\_CLIENT\_ID'\] REDDIT\_CLIENT\_SECRET= os.environ\['REDDIT\_CLIENT\_SECRET'\] REDDIT\_USER\_AGENT   \= os.environ\['REDDIT\_USER\_AGENT'\] SERPAPI\_KEY         \= os.environ\['SERPAPI\_KEY'\] APIFY\_TOKEN         \= os.environ\['APIFY\_TOKEN'\] LISTENNOTES\_KEY     \= os.environ\['LISTENNOTES\_KEY'\] APOLLO\_KEY          \= os.environ\['APOLLO\_KEY'\] ANTHROPIC\_API\_KEY   \= os.environ\['ANTHROPIC\_API\_KEY'\] HUNTER\_KEY          \= os.environ\['HUNTER\_KEY'\] INSTANTLY\_KEY       \= os.environ\['INSTANTLY\_KEY'\] AIRTABLE\_PAT        \= os.environ\['AIRTABLE\_PAT'\] AIRTABLE\_BASE\_ID    \= os.environ\['AIRTABLE\_BASE\_ID'\] \# Thresholds CLAUDE\_SCORE\_THRESHOLD   \= 7      \# min score to proceed to enrichment HUNTER\_CONFIDENCE\_MIN    \= 70     \# min Hunter confidence to use email REDDIT\_DM\_DAILY\_LIMIT    \= 10     \# max Reddit DMs per day SERPAPI\_SLEEP\_SECONDS    \= 1.2    \# sleep between SerpApi calls |
| :---- |

## **9.2  Python dependencies (requirements.txt)**

| google-api-python-client\>=2.100.0  \# YouTube Data API v3 youtube-transcript-api\>=0.6.0 praw\>=7.7.0                         \# Reddit API requests\>=2.31.0 beautifulsoup4\>=4.12.0 newspaper3k\>=0.2.8                  \# article text extraction anthropic\>=0.25.0                   \# Claude API pyairtable\>=2.2.0 python-dotenv\>=1.0.0 flask\>=3.0.0                        \# Instantly webhook receiver itertools                           \# stdlib — matrix generation |
| :---- |

## **9.3  Build order for Claude Code sessions**

* Session 1: Scaffold repo structure, settings.py, schema.py, airtable.py

* Session 2: m3\_serpapi.py (most self-contained, proves Claude scoring end-to-end)

* Session 3: claude\_scorer.py \+ prompts.py — get scoring prompt right before wiring other modules

* Session 4: m1\_youtube.py \+ transcript pipeline

* Session 5: hunter.py \+ contact\_router.py \+ instantly.py

* Session 6: m2\_reddit.py \+ praw\_dm.py \+ manual\_queue.py

* Session 7: m4\_nonprofits.py \+ m5\_professional.py

* Session 8: pipeline.py orchestrator \+ webhook handler \+ end-to-end test

| Start here in Claude Code Open Claude Code and say: "I want to build the book outreach pipeline. Check your memory for the project context.  Let's start with Session 1: scaffold the repo structure, settings.py, schema.py,  and airtable.py as defined in the Engineering Design Document." |
| :---- |

