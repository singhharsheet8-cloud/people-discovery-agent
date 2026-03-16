# People Discovery Agent — Tool Pricing & Cost Estimates

Estimated cost per person discovery: **$0.05 – $0.25** depending on depth and cache hits.

---

## Search & Web Scraping

| Service | What It Does | Pricing | Cost per Discovery |
|---------|-------------|---------|-------------------|
| **Tavily** | Primary web search (AI-optimized) | Free: 1,000/mo; Pay-as-you-go: $0.008/credit | ~$0.04 (5 searches) |
| **Serper.dev** | Google Search, News, Scholar, Patents, Images (fallback) | Starter: $50/50K credits ($1/1K); Scale: $0.50/1K | ~$0.02 (15-20 queries) |
| **SerpAPI** | Google Search (legacy fallback) | $50/mo for 5,000 searches ($0.01/search) | ~$0.10 if used |
| **Firecrawl** | Web page scraping (markdown extraction) | Free: 500 credits; Hobby: $16/mo for 3K; Standard: $83/mo for 100K | ~$0.01 (8-10 pages) |

## LinkedIn Data

| Service | What It Does | Pricing | Cost per Discovery |
|---------|-------------|---------|-------------------|
| **HarvestAPI** | Structured LinkedIn data (exact dates, skills, recommendations, photo) | Pay-as-you-go, ~$0.02-0.05/profile | ~$0.03 (1 profile) |
| **Apify LinkedIn** | LinkedIn profile/posts scraping (403 when credits exhausted) | $49/mo for 100 Actor runs; pay-per-use available | ~$0.05 if used |

## Social Media

| Service | What It Does | Pricing | Cost per Discovery |
|---------|-------------|---------|-------------------|
| **SociaVault** | Instagram profile scraping | Pay-per-request | ~$0.01 |
| **Twitter/X** | Google-based tweet discovery + Nitter/Firecrawl scraping | Free (via Google) + Firecrawl credits | ~$0.005 |

## Free APIs (No Cost)

| Service | What It Does | Notes |
|---------|-------------|-------|
| **GitHub API** | User profiles, repos, contributions | Free with token (5,000 req/hr) |
| **Stack Exchange API** | SO profiles, top answers | Free (300 req/day unauthenticated) |
| **Reddit JSON API** | Subreddit search, user posts | Free (rate-limited) |
| **Medium RSS** | Article discovery by tag | Free |
| **Wikipedia REST API** | Profile images, summaries | Free |
| **YouTube Transcript API** | Video transcript extraction | Free (unofficial library) |

## LLM Costs (per discovery)

| Model | Role | Estimated Cost |
|-------|------|---------------|
| **GPT-4.1-mini** (planning) | Query generation, source scoring | ~$0.01-0.02 |
| **DeepSeek Chat** (synthesis) | Final profile write-up | ~$0.01-0.03 |
| **GPT-4.1-mini** (reasoning) | Disambiguation, analysis | ~$0.01-0.02 |

## Total Estimated Cost per Discovery

| Scenario | Cost |
|----------|------|
| **Cached (repeat discovery)** | ~$0.01-0.02 |
| **Standard (new person, Tavily + HarvestAPI)** | ~$0.10-0.15 |
| **Deep (multi-turn, all sources)** | ~$0.15-0.25 |
| **Maximum (all APIs, no cache)** | ~$0.30-0.50 |

---

## API Key Configuration

All keys are set in `backend/.env`:

```
TAVILY_API_KEY=tvly-dev-...
SERPER_API_KEY=...
FIRECRAWL_API_KEY=...
HARVESTAPI_API_KEY=...
APIFY_API_KEY=...
GITHUB_TOKEN=...
SOCIAVAULT_API_KEY=...
OPENAI_API_KEY=...
DEEPSEEK_API_KEY=...
```

## Priority Order (fallback chain)

1. **Tavily** → Serper → SerpAPI (web search)
2. **HarvestAPI** → Firecrawl → Google snippet → Apify (LinkedIn)
3. **SociaVault** → Google fallback (Instagram)
4. **Google search** → Firecrawl → Apify (Twitter, Reddit, Medium)
5. **GitHub API** direct (GitHub)
6. **Free APIs** direct (Stack Exchange, Wikipedia, YouTube)
