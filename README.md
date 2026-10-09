# RSS to X Auto-Poster

Checks an RSS feed on a schedule and posts each new item to X (Twitter) with its picture. Built for the Crunchyroll feed, it posts English items only. It runs on GitHub Actions.

## What a post looks like

```
Detective Conan (1214-current) - Episode 1215 - The Crimson Closing Day (The Penultimate Show)

Actors fall to their deaths one after another at a theater in Osaka.
```

plus the item's 640x360 picture. There is no link in the post.

## What it does

- Reads the feed and posts only items it hasn't posted before
- **English only:** skips items whose title has a language tag such as `(Telugu Dub)` or `(Polish Dub)`. Items with no tag, or `(English Dub)`, are posted.
- Posts the oldest new item first, up to **5 per run**. Any extra items wait for the next run.
- Trims the text to fit X's character limit
- Stops at the first failure, so a broken setup doesn't keep spending credits
- Won't post without an image unless you allow it
- Remembers what it posted in `seen_x.json`. The first run records the current items and posts nothing.

## Cost

New X developer accounts have no free tier. They pay per post from credits you add. At the time of writing a plain post costs about $0.015, but check the billing page in the X console for current rates, including whether image uploads are charged. Add only a small amount of credit at first. When it runs out, posting simply fails.

## Files

| File | Purpose |
|---|---|
| `x_bot.py` | The bot |
| `requirements.txt` | Python packages (`feedparser`, `requests`, `requests-oauthlib`) |
| `.github/workflows/x-post.yml` | The schedule and run steps |
| `seen_x.json` | Created automatically; list of posted items |

## Setup

1. Sign in to the X developer console (console.x.com) and create an app. Choose **Web App, Automated App or Bot**, and fill the required web address fields with any valid link.
2. Set the app's permissions to **Read and write**.
3. Open **Keys and tokens**. Generate the **API Key and Secret**, then the **Access Token and Secret**. Generate the access token after setting permissions, and check it says Read and Write. X shows each secret only once, so copy them right away.
4. Add a small amount of credit in the console's billing section.
5. In this repo, go to **Settings → Secrets and variables → Actions** and add five repository secrets:

   | Name | Value |
   |---|---|
   | `FEED_URL` | the RSS link, for example `https://www.crunchyroll.com/rss` |
   | `X_API_KEY` | API Key |
   | `X_API_SECRET` | API Key Secret |
   | `X_ACCESS_TOKEN` | Access Token |
   | `X_ACCESS_TOKEN_SECRET` | Access Token Secret |

6. Make sure the workflow is at `.github/workflows/x-post.yml`.
7. Test the image upload: **Actions → Post to X → Run workflow**, mode `upload_test`. The log should say `Upload test OK`. This posts nothing.
8. Run the workflow again with mode `normal`. This records the current items.
9. From then on it runs every hour and posts new English items.

## Configuration

| Variable | Default | What it does |
|---|---|---|
| `RUN_MODE` | `normal` | `upload_test` only tests the image upload |
| `MAX_POSTS_PER_RUN` | `5` | Most posts in a single run |
| `ENGLISH_ONLY` | `1` | Set to `0` to post every language |
| `ALLOW_TEXT_ONLY` | `0` | Set to `1` to post even if the image fails |
| `SEEN_FILE` | `seen_x.json` | Where posted items are saved |

The workflow only passes `RUN_MODE` and the secrets. To change another setting, add it under `env:` in `x-post.yml`.

## Changing the schedule

Edit the `cron` line in `x-post.yml`. The default `"17 * * * *"` means minute 17 of every hour. GitHub's scheduler is best-effort, so runs can start late or be skipped.

## Troubleshooting

| Problem | Likely cause and fix |
|---|---|
| `Upload test FAILED` | Read the HTTP status above that line. `401` or `403` usually means a wrong key, or the access token was made before the app had Read and write permission. Fix the permission and regenerate the token. |
| `Post failed` with a credit or billing message | Add credit in the X console. |
| `Post failed` about duplicate content | X rejects identical text. It should be rare because every episode title differs. |
| `Invalid URL '': No scheme supplied` | The `FEED_URL` secret is missing or misspelled. |
| `No image attached, so not posting` | The image couldn't be uploaded. Run `upload_test` to see why. |
| Green run, nothing posted | No new English items since the last run. The log shows how many were skipped. |
| `Cap reached` | Normal after a big release day. The rest post on the next runs. |

## Security

Never put the API keys or tokens in the code, a commit, a screenshot or a chat. They belong only in GitHub secrets. If one leaks, regenerate it in the X console.

## Run it on your own computer

```
pip install -r requirements.txt
export FEED_URL=... X_API_KEY=... X_API_SECRET=... X_ACCESS_TOKEN=... X_ACCESS_TOKEN_SECRET=...
python x_bot.py
```
