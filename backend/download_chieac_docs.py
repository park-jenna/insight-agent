"""
Download the ChiEAC public document corpus.

All sources are official and public: ISAC (Illinois Student Assistance
Commission), City Colleges of Chicago, TheDream.US, and ISBE (Illinois
State Board of Education). Nothing here is private or scraped, these are
guides any student or advocate can download.

Saves into ./documents/chieac/. Run with: python download_chieac_docs.py

Note: a couple of these URLs may go stale over time as agencies update
their sites. The script reports which ones fail so you can swap them.
"""

import os
import urllib.request
import urllib.error

OUT_DIR = os.path.join("documents", "chieac")

# (filename to save as, source url)
DOCS = [
    # RISE Act / Alternative Application for Illinois Financial Aid
    ("isac_alt_app_worksheet_25-26.pdf",
     "https://www.isac.org/students/before-college/documents/25-26AltAppWorksheet.pdf"),
    ("isac_alt_app_worksheet_26-27.pdf",
     "https://www.isac.org/students/before-college/documents/26-27AltAppWorksheet.pdf"),
    ("isac_alt_app_user_guide_25-26.pdf",
     "https://www.isac.org/students/before-college/documents/25-26AltAppUserGuide.pdf"),

    # Chicago Star Scholarship
    ("ccc_star_scholarship_faq.pdf",
     "https://colleges.ccc.edu/app/uploads/STAR_Student_FAQs_4.13.2023-1.pdf"),
    ("ccc_financial_aid_guide_25-26.pdf",
     "https://www.ccc.edu/wp-content/uploads/departments_Documents_FinancialAid_CCCFinancialAidGuide_2025_2026.pdf"),
    ("ccc_star_scholarship_brochure.pdf",
     "https://toolkit.ccc.edu/wp-content/uploads/2019/01/Star-Scholarship-Brochure-Student-JAN-2019.pdf"),

    # TheDream.US National Scholarship
    ("thedreamus_national_guide_25-26.pdf",
     "https://www.thedream.us/wp-content/uploads/2025/06/2025-26-TheDream.US-National-Application-Guide-updated-language.pdf"),

    # IEP / special education advocacy (ISBE)
    ("isbe_parent_guide_special_ed.pdf",
     "https://www.isbe.net/Documents/Parent-Guide-Special-Ed.pdf"),
    ("isbe_special_ed_admin_code_226.pdf",
     "https://www.isbe.net/documents/226ark.pdf"),
    ("isbe_consent_forms_instructions.pdf",
     "https://www.isbe.net/documents/consent_forms_instruct.pdf"),
]

# some agency sites reject the default urllib agent, so pretend to be a browser
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/120.0 Safari/537.36"
}


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    ok, failed = 0, []

    for filename, url in DOCS:
        dest = os.path.join(OUT_DIR, filename)
        print(f"  downloading {filename} ... ", end="", flush=True)
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = resp.read()
            with open(dest, "wb") as f:
                f.write(data)
            kb = len(data) / 1024
            print(f"ok ({kb:.0f} KB)")
            ok += 1
        except Exception as e:
            print(f"FAILED ({type(e).__name__})")
            failed.append((filename, url, str(e)))

    print(f"\nDownloaded {ok}/{len(DOCS)} into ./{OUT_DIR}/")
    if failed:
        print("\nThese failed, you can open the URL in a browser to grab them manually:")
        for filename, url, err in failed:
            print(f"  {filename}")
            print(f"    {url}")


if __name__ == "__main__":
    main()
