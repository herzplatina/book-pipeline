**Why I Feel the Universe Loves Me**

Engineering Design Document (EDD)

Lead Discovery, Scoring, Enrichment & Outreach Pipeline

Version 1.0 | May 2026

# **1\. System Overview**

This document defines the technical architecture, data flow, API integrations, and variable schemas for the five-stage lead generation pipeline. It is written for use with Claude Code and covers every module from raw discovery to Airtable CRM entry and Hunter Sequences outreach dispatch. Hunter.io is the single vendor for both email enrichment and automated outreach — Instantly.ai is no longer used.

## **1.1 Five-stage pipeline summary**

- Stage 1 — Discover: four active sources (SerpApi, YouTube, Reddit, ListenNotes) each produce a raw leads list as JSON. Apify, Apollo, and nonprofit/archive scraping are paused and will be revisited later.

- Stage 2 — Score: Claude API Haiku 4.5 reads each raw lead, returns score (1–10), extracted name, archetype match, one-sentence summary

- Stage 3 — Enrich: Hunter.io finds and verifies email for leads with professional footprint; platform channels used for others

- Stage 4 — Outreach: Hunter Sequences for automated archetypes; PRAW / manual for sensitive archetypes

- Stage 5 — CRM: Airtable stores all leads with full field schema; Hunter webhooks update status automatically

## **1.2 Repository structure**

| book-pipeline/ config/ settings.py \# env-driven settings and source matrices modules/ m1_youtube.py \# YouTube Data API v3 \+ transcript fetch m2_reddit.py \# PRAW live \+ Arctic Shift archive m3_serpapi.py \# SerpApi matrix \+ article fetch \+ dedup m4_nonprofits.py \# active ListenNotes search; nonprofit/Apify helpers paused m5_apollo.py \# Apollo.io module paused scoring/ claude_scorer.py \# Claude API Haiku scoring engine prompts.py \# scoring prompt templates per archetype enrichment/ hunter.py \# email find \+ verify waterfall outreach/ hunter_sequences.py \# Hunter Sequences API — lead add \+ campaign dispatch crm/ airtable.py \# Airtable API read/write, status transitions schema.py \# field definitions and validation pipeline.py \# master orchestrator — runs active default sources requirements.txt |
| :------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |

# **2\. Complete API & Tool Reference**

All tools used across active and paused modules, with authentication method, cost, and key variables.

| Tool / API                | Module            | Cost              | Auth method                                              | Key variables / endpoints                                                         |
| :------------------------ | :---------------- | :---------------- | :------------------------------------------------------- | :-------------------------------------------------------------------------------- |
| YouTube Data API v3       | M1                | Free              | API key (GCP)                                            | q, type=video, maxResults, videoDuration                                          |
| youtube-transcript-api    | M1                | Free              | None required                                            | YouTubeTranscriptApi.get_transcript(video_id)                                     |
| requests \+ BeautifulSoup | M4 paused helpers | Free              | None                                                     | Future nonprofit/archive scraping candidates; not active in YouTube               |
| Reddit PRAW               | M2                | Free              | OAuth2 (client_id, client_secret, user_agent)            | subreddit.search(query, limit, time_filter), redditor.message()                   |
| Arctic Shift API          | M2                | Free              | None                                                     | GET /api/posts?q=\&subreddit=\&after=\&before=                                    |
| SerpApi (Google engine)   | M3                | Free / $50 Basic  | api_key param                                            | engine=google, q, location, gl, hl, as_qdr=custom, tbs=cdr:1,cd_min:,cd_max:, num |
| newspaper3k               | M3                | Free              | None                                                     | Article(url).download().parse() → .text, .authors                                 |
| Apify web scraper         | PAUSED            | Free tier         | APIFY_TOKEN env var                                      | Future candidate; revisit later                                                   |
| ListenNotes API           | M4                | Free (10/mo)      | X-ListenAPI-Key header                                   | GET /api/v2/search?q=\&type=episode\&language=English                             |
| Apollo.io API             | PAUSED            | Free (50 exports) | api_key in JSON body                                     | Future candidate; revisit later                                                   |
| Claude API (Haiku 4.5)    | Scoring           | \~$5/mo           | x-api-key header (Anthropic)                             | model, max_tokens, messages, system prompt with archetype schema                  |
| Hunter.io Email Finder    | Enrichment        | $49/mo Starter    | api_key param (HUNTER_KEY)                               | GET /v2/email-finder?domain=\&first_name=\&last_name=                             |
| Hunter.io Verifier        | Enrichment        | Included          | api_key param (HUNTER_KEY)                               | GET /v2/email-verifier?email=                                                     |
| Hunter Sequences API      | Outreach          | Included in plan  | api_key param — **same HUNTER_KEY, no extra credential** | POST /v2/campaigns/{id}/recipients — add lead to sequence                         |
| Airtable API              | CRM               | Free              | Authorization: Bearer PAT                                | POST/PATCH /v0/{baseId}/{tableId} — records array with fields object              |
| Make.com (optional)       | Orchestration     | $9/mo Core        | Webhook triggers                                         | HTTP module, Airtable module, Hunter webhook module                               |

# **3\. Stage 1 — Discovery Modules**

## **Module 1 — YouTube discovery**

### **Variable schema**

| YOUTUBE_SEARCH_QUERIES \= { 'health': \['Joe Dispenza healing miracle', 'spontaneous remission story', 'healed from cancer story', 'mental health recovery transformation'\], 'driver': \['Uber driver entrepreneur story', 'gig worker building business', 'driving for Uber while building startup'\], 'criminal':\['life after prison success', 'reformed criminal entrepreneur', 'formerly incarcerated second chance story'\] } YOUTUBE_FILTERS \= { 'videoDuration': 'medium', \# 4–20 min — personal testimonials, not lectures 'type': 'video', 'maxResults': 50, 'order': 'relevance' } |
| :----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |

### **Data flow**

| \#    | Step name               | Input                              | Process                                                                 | Output                                                              |
| :---- | :---------------------- | :--------------------------------- | :---------------------------------------------------------------------- | :------------------------------------------------------------------ |
| **1** | **YouTube search**      | query string per archetype         | YouTube Data API v3 search.list()                                       | list of {video_id, title, description, channel_title, channel_url}  |
| **2** | **Transcript fetch**    | video_id                           | youtube-transcript-api.get_transcript()                                 | raw transcript text string                                          |
| **3** | **Parse contact hints** | video description + transcript     | regex extraction for email addresses and conservative name phrases only | `_emails`, `_name_candidates`, `_contact_clue` when an email exists |
| **4** | **Score**               | title + description + transcript   | Claude API scorer (see Stage 2\)                                        | score, name, archetype_match, summary                               |
| **5** | **Route contact**       | score ≥ 7 + extracted email if any | direct email if present; otherwise manual/platform review               | contact_method, contact_value                                       |

YouTube contact hints are intentionally limited to video description text and transcript text. The module does not inspect channel URLs, channel IDs, channel About pages, or channel metadata for contact discovery.

For leads that pass the Claude score threshold, the YouTube channel URL is retained for review: it is logged, written to the run checkpoint artifact, and sent to Airtable as `Channel URL`. This is for manual follow-up only when direct email extraction is unavailable.

## **Module 2 — Reddit discovery**

### **Variable schema**

| SUBREDDITS \= { 'driver': \['UberDrivers', 'lyftdrivers', 'gig_economy'\], 'criminal': \['offmychest', 'reentry', 'excons'\], 'health': \['addiction', 'Recovery', 'CPTSD', 'offmychest'\], 'bluecollar': \['AskWorkplace', 'jobs', 'careerguidance'\] } REDDIT_KEYWORDS \= \[ 'started a business', 'entrepreneur', 'built something', 'second chance', 'turned my life around', 'got out and', 'healed from', 'sober and now', 'lost my job and' \] REDDIT_FILTERS \= { 'min_score': 100, \# upvotes — proxy for story quality 'time_filter': 'year', 'limit': 100 } ARCTIC_SHIFT_DATE_RANGE \= { 'after': '2020-01-01', 'before': '2023-12-31' } |
| :-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |

### **Data flow**

| \#    | Step name               | Input                     | Process                             | Output                                                 |
| :---- | :---------------------- | :------------------------ | :---------------------------------- | :----------------------------------------------------- |
| **1** | **Live subreddit scan** | subreddit name \+ keyword | praw.subreddit().search()           | list of {post_id, author, title, selftext, score, url} |
| **2** | **Archive scan**        | subreddit \+ date range   | Arctic Shift API GET /api/posts     | historical posts 2020–2023                             |
| **3** | **Score post**          | selftext                  | Claude API scorer                   | score, name_if_revealed, archetype_match               |
| **4** | **Draft DM**            | score ≥ 7, post_id        | praw_dm.py draft_message(post_id)   | draft message string — ENTERS HUMAN REVIEW QUEUE       |
| **5** | **Human approves**      | draft message             | Manual review — human triggers send | PRAW redditor.message() called                         |

| ✋ HANDCRAFT REQUIRED All Reddit DMs enter a human review queue before sending — never auto-send. Reference the specific post in the opening line of every DM. Maximum 10 DMs per day per Reddit account to avoid spam flags. Do not attempt Hunter.io on Reddit usernames — no domain, hit rate \<2%. |
| :----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |

## **Module 3 — SerpApi local news (blue-collar archetype)**

### **Variable schema**

| CITIES \= \[ ('Detroit, Michigan, United States', \['detroitnews.com','freep.com','mlive.com'\]), ('Pittsburgh, Pennsylvania, United States', \['post-gazette.com','wesa.fm','triblive.com'\]), ('Cleveland, Ohio, United States', \['cleveland.com','crainscleveland.com','ideastream.org'\]), ('Tulsa, Oklahoma, United States', \['tulsaworld.com','tulsapeople.com','kjrh.com'\]), ('Louisville, Kentucky, United States', \['courier-journal.com','wdrb.com','louisvillemag.com'\]), ('Memphis, Tennessee, United States', \['commercialappeal.com','dailymemphian.com','wreg.com'\]), ('Fresno, California, United States', \['fresnobee.com','kvpr.org','abc30.com'\]), ('El Paso, Texas, United States', \['elpasotimes.com','kvia.com','elpasomatters.org'\]) \] DATE_WINDOWS \= \[ ('1/1/2020', '6/30/2020', 'early_covid'), ('7/1/2020', '12/31/2020', 'late_covid'), ('1/1/2021', '6/30/2021', 'rebuild_early'), \# PRIORITY ('7/1/2021', '12/31/2021', 'rebuild_peak'), \# PRIORITY ('1/1/2022', '12/31/2022', 'established'), ('1/1/2023', '12/31/2023', 'lookback') \] QUERY_TERMS \= \[ '"lost job" "Covid" "started"', '"laid off" "pandemic" "built"', '"Covid" "layoff" "comeback"', '"lost everything" "Covid" "now"', '"pandemic" "unemployed" "entrepreneur"', '"furloughed" "Covid" "new business"' \] SERPAPI_PARAMS_TEMPLATE \= { 'engine': 'google', 'gl': 'us', 'hl': 'en', 'as_qdr': 'custom', 'num': 10, 'api_key': SERPAPI_KEY \# tbs, q, location injected per matrix cell } |
| :---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |

### **Data flow**

| \#    | Step name          | Input                               | Process                                                          | Output                                                      |
| :---- | :----------------- | :---------------------------------- | :--------------------------------------------------------------- | :---------------------------------------------------------- |
| **1** | **Build matrix**   | CITIES × DATE_WINDOWS × QUERY_TERMS | itertools.product() — 288 combos full / 90 reduced               | list of (city, sites, cd_min, cd_max, window, query)        |
| **2** | **SerpApi call**   | one matrix cell                     | requests.get serpapi.com/search — q \= query \+ site:A OR site:B | {organic_results: \[{title, link, snippet, date, source}\]} |
| **3** | **Deduplicate**    | all results so far                  | seen_urls set — skip if url already processed                    | unique article list                                         |
| **4** | **Fetch article**  | article URL                         | newspaper3k Article(url).parse()                                 | full text, authors list                                     |
| **5** | **Claude extract** | article full text                   | Claude API: extract named individual \+ score story fit          | name, score, summary, archetype_match                       |
| **6** | **Contact route**  | name, article source domain         | if business_owner: Hunter domain search; else: journalist email  | email or journalist_contact                                 |

| Rate limiting Sleep 1.2 seconds between SerpApi calls to stay within rate limits. Full matrix (288 calls) requires SerpApi Basic plan at $50/mo. Reduced matrix (5 cities × 6 windows × 3 queries \= 90 calls) fits within free tier. |
| :------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |

## **Module 4 — ListenNotes podcast discovery**

### **Key sources and scraping targets**

| LISTENNOTES_QUERIES \= \[ 'former prisoner entrepreneur', 'Joe Dispenza healing story', 'Covid job loss rebuilt life', 'deradicalization story', 'addiction recovery second career' \] NONPROFIT_URLS / StoryCorps / Moth / Apify targets are paused for now and remain future candidates. |
| :----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |

### **Data flow**

| \#    | Step name              | Input                        | Process                                                   | Output                                               |
| :---- | :--------------------- | :--------------------------- | :-------------------------------------------------------- | :--------------------------------------------------- |
| **1** | **ListenNotes search** | query list                   | GET /api/v2/search?q=\&type=episode                       | {podcast_name, episode_title, description, pub_date} |
| **2** | **Normalize lead**     | episode result               | title + description become `_content`; source=listennotes | canonical raw lead dict                              |
| **3** | **Score all**          | episode title + description  | Claude API scorer per record                              | score, archetype_match, summary                      |
| **4** | **Future paused work** | nonprofit/Apify/archive URLs | not active in default pipeline                            | revisit after current four-source pipeline is stable |

| ✋ HANDCRAFT REQUIRED Nonprofit alumni and Life After Hate contacts MUST go to manual_queue — never automated sequence outreach. The org comms director email is the first handcrafted message, not contact to the individual. Do not attempt Hunter.io for StoryCorps or annual report subjects — hit rate under 15%. |
| :--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |

## **Module 5 — Professional discovery (paused)**

### **Apollo.io search filter schema — paused for later**

| APOLLO_SEARCH_PAYLOAD \= { 'api_key': APOLLO_KEY, 'q_organization_industry_tag_ids': \[ \# blue-collar industries 'manufacturing', 'construction', 'transportation', 'hospitality', 'retail', 'food_and_beverage' \], 'employment_history': { 'end_date_range': {'min': '2020-01-01', 'max': '2021-06-30'}, \# job ended during Covid 'current': False }, 'q_keywords': 'founder OR owner OR started OR built OR launched', 'page': 1, 'per_page': 50 } |
| :------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |

| \#    | Step name          | Input                        | Process                                                      | Output                                                               |
| :---- | :----------------- | :--------------------------- | :----------------------------------------------------------- | :------------------------------------------------------------------- |
| **1** | **Apollo search**  | filter payload above         | POST /v1/mixed_people/search                                 | list of {first_name, last_name, title, company, email, linkedin_url} |
| **2** | **Email check**    | Apollo response              | if email present in Apollo: use it; else: Hunter fallback    | verified_email or None                                               |
| **3** | **Score profile**  | title \+ company description | Claude API: does employment gap suggest Covid pivot story?   | score, story_hypothesis                                              |
| **4** | **LinkedIn queue** | profiles with no email found | manual_queue.py LinkedIn tab — for manual connection request | Airtable record with channel=LinkedIn                                |

# **4\. Stage 2 — Claude API Scoring Engine**

## **4.1 Scoring prompt template**

| SYSTEM_PROMPT \= '''You are a story evaluator for a book about human transformation. You will receive a piece of text (transcript, Reddit post, or article excerpt). Return ONLY a JSON object with these exact fields: { "score": \<integer 1-10\>, "name": \<string or null — extracted full name if mentioned\>, "archetype": \<one of: extremist, criminal, health, driver, bluecollar, other\>, "archetype_match": \<true or false\>, "turning_point": \<string — one sentence describing the specific moment of change, or null\>, "summary": \<string — one sentence describing the story\>, "contact_clue": \<string or null — any email, website, social handle mentioned\> } Score 8-10: vivid, specific turning point, named individual, emotionally resonant. Score 5-7: clear transformation arc but vague on the turning point moment. Score 1-4: generic, no named individual, no specific transformation event. Return ONLY the JSON object. No preamble, no explanation.''' def score_content(text, archetype_hint=None): user_msg \= f'Archetype hint: {archetype_hint}\\n\\nContent:\\n{text\[:4000\]}' response \= anthropic_client.messages.create( model='claude-haiku-4-5-20251001', max_tokens=300, system=SYSTEM_PROMPT, messages=\[{'role': 'user', 'content': user_msg}\] ) return json.loads(response.content\[0\].text) |
| :--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |

## **4.2 Scoring thresholds**

- Score ≥ 8: Auto-approve for enrichment and outreach pipeline

- Score 6–7: Add to Airtable with status=NeedsReview — human decides

- Score ≤ 5: Discard — do not enrich or contact

- archetype_match \= false: Flag for manual review regardless of score

# **5\. Stage 3 — Enrichment & Contact Routing**

## **5.1 Contact router logic**

| def route_contact(lead: dict) \-\> dict: source \= lead\['source'\] \# Sources where Hunter is unlikely to work if source in \['reddit', 'youtube_personal', 'storycorps', 'nonprofit_annual_report'\]: return platform_channel(lead) \# Reddit DM, YouTube DM, org intro \# Sources where Hunter works well if source in \['apollo', 'tedx', 'moth', 'podcast_guest', 'news_business_owner'\]: email \= hunter_find(lead\['name'\], lead\['employer_domain'\]) if email and email\['confidence'\] \>= 70: verified \= hunter_verify(email\['value'\]) if verified\['result'\] \== 'deliverable': return {'method': 'email', 'value': email\['value'\], 'channel': 'hunter_sequence'} \# Sensitive archetypes — always manual regardless of email availability if lead\['archetype'\] in \['extremist', 'criminal'\] and lead\['source'\] \== 'nonprofit': return {'method': 'org_intro', 'value': lead\['org_comms_email'\], 'channel': 'manual', 'requires_handcraft': True} \# Fallback: platform channel return platform_channel(lead) |
| :----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |

## **5.2 Hunter API call pattern**

| import requests def hunter_find(first_name, last_name, domain): resp \= requests.get('https://api.hunter.io/v2/email-finder', params={ 'domain': domain, 'first_name': first_name, 'last_name': last_name, 'api_key': HUNTER_KEY }) data \= resp.json()\['data'\] return data if data.get('confidence', 0\) \>= 70 else None def hunter_verify(email): resp \= requests.get('https://api.hunter.io/v2/email-verifier', params={ 'email': email, 'api_key': HUNTER_KEY }) return resp.json()\['data'\] \# result: 'deliverable' | 'risky' | 'undeliverable' |
| :----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------- | --------------- |

# **6\. Stage 4 — Outreach**

## **6.1 Hunter Sequences lead add and campaign assignment**

> **Note:** Hunter Sequences sends through your own connected Gmail / Google Workspace / Outlook inbox. It has no built-in email warm-up. If the sending inbox is new, warm it manually before activating campaigns. No separate credential required — uses the same HUNTER_KEY as enrichment.

| HUNTER_SEQUENCE_ID \= 'sequence_id_book_outreach' def add_to_hunter_sequence(lead: dict): payload \= { 'emails': \[lead\['verified_email'\]\], 'first_name': lead\['first_name'\], 'last_name': lead\['last_name'\], 'opening_line': lead\['opening_line'\], \# SET THIS — never leave blank 'custom_variables': { 'story_source': lead\['source'\], 'story_summary': lead\['claude_summary'\], 'city': lead.get('city', ''), 'archetype': lead\['archetype'\] } } resp \= requests.post( f'https://api.hunter.io/v2/campaigns/{HUNTER_SEQUENCE_ID}/recipients', params={'api_key': HUNTER_KEY}, json=payload ) return resp.json() \# returns {recipients_added, skipped_recipients} |
| :----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |

## **6.2 Handcraft-required outreach — manual queue**

| ✋ HANDCRAFT REQUIRED The following lead types are NEVER sent to Hunter Sequences. They enter manual_queue in Airtable: 1\. archetype \= 'extremist' — ALL contacts, every source 2\. archetype \= 'criminal' AND source \= 'nonprofit' or 'org_intro' 3\. source \= 'local_news' AND contact_method \= 'journalist_intro' 4\. source \= 'storycorps' or 'annual_report' 5\. status \= 'Responded' — any archetype, any source For items 1–4: write a fresh personalised email. Do not use templates. For item 5: automation ends at first reply. Every subsequent message is handcrafted. Review gate: inspect 5 sample sequence emails before activating any new campaign. |
| :--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |

## **6.3 Reddit DM review queue**

| def queue_reddit_dm(lead: dict): '''Adds drafted DM to Airtable manual review queue — does NOT send.''' draft \= generate_reddit_dm_draft( username=lead\['reddit_username'\], post_title=lead\['post_title'\], post_snippet=lead\['post_text'\]\[:200\], archetype=lead\['archetype'\] ) airtable.create_record('Manual DM Queue', { 'Username': lead\['reddit_username'\], 'Post URL': lead\['post_url'\], 'Draft Message': draft, 'Status': 'Awaiting Review', 'Channel': 'Reddit DM' }) \# Human opens Airtable, reviews draft, edits if needed, \# changes Status to 'Approved', then triggers send_approved_dms() |
| :---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |

# **7\. Stage 5 — Airtable CRM Schema**

## **7.1 Contacts table fields**

| CONTACTS_FIELDS \= { 'Name': str, \# extracted by Claude or from source 'First Name': str, 'Last Name': str, 'Archetype': enum, \# extremist | criminal | health | driver | bluecollar 'Source': str, \# youtube | reddit | serpapi | nonprofit | apollo | ... 'Source URL': str, \# link to original video/post/article 'Channel URL': str, \# YouTube channel URL for qualified YouTube leads, manual follow-up only 'City': str, 'Date Window': str, \# SerpApi window label e.g. rebuild_peak 'Claude Score': int, \# 1–10 'Story Summary': str, \# one sentence from Claude 'Turning Point': str, \# extracted by Claude if present 'Email': str, \# verified by Hunter 'Email Confidence': int, \# Hunter confidence score 0–100 'Contact Method': enum, \# email | reddit_dm | instagram_dm | org_intro | linkedin 'Contact Value': str, \# the actual email/handle/URL 'Requires Handcraft': bool, \# True for extremist, criminal-org, journalist-intro 'Status': enum, \# New | Contacted | Responded | Pre-screened | Shortlisted | Declined | Bounced 'Hunter Lead ID':str, \# returned by Hunter Sequences API on recipient add 'Hunter Sequence ID': str, \# Hunter Sequence recipient was added to 'Email Opened': bool, \# set by Hunter webhook 'Replied': bool, \# set by Hunter webhook 'Reply Sentiment': enum, \# positive | neutral | unsubscribe | bounce 'Pre-screen Notes': str, \# your notes from the 10-min call 'Turning Point Answer': str,\# their verbatim answer to the key question 'Shortlisted': bool, 'Interview Date': date, 'Consent Received': bool, 'Created At': datetime } |
| :------------------------------------------------------------------------------------------------------------------------------------------- | -------- | ------ | ------ | ------------------------------------ | ------ | ------- | --------- | ------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | --------- | ------------ | --------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------- | --------- | ------------ | ----------- | -------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------- | ----------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |

## **7.2 Hunter Sequences webhook handler**

> Configure the webhook URL in the Hunter dashboard under Settings → Integrations → Webhooks. Hunter fires events for: reply received, unsubscribe, bounce, sequence completed.

| from flask import Flask, request app \= Flask(\_\_name\_\_) @app.route('/webhook/hunter', methods=\['POST'\]) def hunter_webhook(): event \= request.json lead_email \= event.get('email') \# Hunter webhook payload field event_type \= event.get('type') \# 'reply' | 'open' | 'unsubscribe' | 'bounce' | 'completed' sentiment \= event.get('reply_category', 'neutral') \# positive | neutral | unsubscribe record \= airtable.find_by_email(lead_email) if not record: return '', 200 if event_type \== 'open': airtable.update(record\['id'\], {'Email Opened': True}) elif event_type \== 'reply': airtable.update(record\['id'\], { 'Status': 'Responded', 'Replied': True, 'Reply Sentiment': sentiment }) elif event_type \== 'bounce': airtable.update(record\['id'\], {'Status': 'Bounced', 'Replied': False}) else: airtable.update(record\['id'\], {'Replied': True, 'Reply Sentiment': sentiment}) return '', 200 |
| :-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------ | ------------- | -------- | --------------------------------------------------------------------------- | ------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |

# **8\. Master Pipeline Orchestrator**

| \# pipeline.py — active default sources def run_pipeline(): all_raw_leads \= \[\] \# Stage 1 — Discovery all_raw_leads \+= m1_youtube.discover() all_raw_leads \+= m2_reddit.discover() all_raw_leads \+= m3_serpapi.discover() \# sleeps 1.2s between calls all_raw_leads \+= m4_nonprofits.discover() \# ListenNotes only by default \# Apify / nonprofit scraping / Apollo are paused for later \# Stage 2 — Score scored \= \[claude_scorer.score(lead) for lead in all_raw_leads\] qualified \= \[l for l in scored if l\['score'\] \>= 7\] \# Stage 3 — Enrich + route enriched \= \[contact_router.route(lead) for lead in qualified\] \# Stage 4 — Outreach / manual queue \# Stage 5 — CRM airtable.upsert(lead) for each lead |
| :-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |

# **9\. Environment & Configuration**

## **9.1 Required environment variables**

| Active source credentials: YOUTUBE_API_KEY, REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USER_AGENT, SERPAPI_KEY, LISTENNOTES_KEY, ANTHROPIC_API_KEY, HUNTER_KEY, AIRTABLE_PAT, AIRTABLE_BASE_ID, HUNTER_SEQUENCE_ID. Paused/future credentials: APIFY_TOKEN and APOLLO_KEY. Thresholds: CLAUDE_SCORE_THRESHOLD \= 7, HUNTER_CONFIDENCE_MIN \= 70, REDDIT_DM_DAILY_LIMIT \= 10, SERPAPI_SLEEP_SECONDS \= 1.2. |
| :-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |

## **9.2 Python dependencies (requirements.txt)**

| google-api-python-client\>=2.100.0 \# YouTube Data API v3 youtube-transcript-api\>=0.6.0 praw\>=7.7.0 \# Reddit API requests\>=2.31.0 beautifulsoup4\>=4.12.0 newspaper3k\>=0.2.8 \# article text extraction anthropic\>=0.25.0 \# Claude API pyairtable\>=2.2.0 python-dotenv\>=1.0.0 flask\>=3.0.0 \# Hunter webhook receiver itertools \# stdlib — matrix generation |
| :---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |

## **9.3 Build order for Claude Code sessions**

- Session 1: Scaffold repo structure, settings.py, schema.py, airtable.py

- Session 2: m3_serpapi.py (most self-contained, proves Claude scoring end-to-end)

- Session 3: claude_scorer.py \+ prompts.py — get scoring prompt right before wiring other modules

- Session 4: m1_youtube.py \+ transcript pipeline

- Session 5: hunter.py \+ contact_router.py \+ hunter_sequences.py

- Session 6: m2_reddit.py \+ praw_dm.py \+ manual_queue.py

- Session 7: m4_nonprofits.py \+ m5_professional.py

- Session 8: pipeline.py orchestrator \+ webhook handler \+ end-to-end test

| Start here in Claude Code Open Claude Code and say: "I want to build the book outreach pipeline. Check your memory for the project context. Let's start with Session 1: scaffold the repo structure, settings.py, schema.py, and airtable.py as defined in the Engineering Design Document." |
| :------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
