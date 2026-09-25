# Job Agent MVP

$0-first job monitor for Yohannes.

## Run model

GitHub Actions runs the scanner approximately every 10 minutes. The scan uses public Greenhouse, Lever, and Ashby job feeds first, then filters and matches jobs before storing qualified/review candidates in Supabase.

## GitHub Actions secrets

Repository -> Settings -> Secrets and variables -> Actions:

- `SUPABASE_URL` = `https://bovpcfirhvpocurjtnts.supabase.co`
- `SUPABASE_SERVICE_ROLE_KEY` = the **service-role secret** from Supabase Project Settings -> API.

Never put the service-role secret in source code.

## Current filters

- Remote or hybrid only
- Maryland, Virginia, Washington, DC, or U.S. remote
- Full-time or contract
- Full-time minimum: $80,000
- Contract minimum: $50/hour when hourly compensation is explicitly available
- Microsoft Power Platform / Microsoft ecosystem skills
- Title is not a hard whitelist; skill match can qualify a differently titled role
- Duplicate protection by job URL
- User remains final application submitter

## Current ATS sources seeded in Supabase

- Accenture Federal Services (Greenhouse)
- Blue Water Thinking (Greenhouse)
- Dev Technology (Greenhouse)
- TrueTandem (Lever)
- Synergy ECP (Lever)
- D.A. Davidson (Lever)
- MCA Connect (Lever)
- PALO IT (Ashby)

More public ATS boards can be added to the `job_sources` table without changing the scanner.
