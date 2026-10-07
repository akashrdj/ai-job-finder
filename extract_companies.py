import zipfile
import xml.etree.ElementTree as ET
import json
from collections import defaultdict
from pathlib import Path

def extract_recruiter_data():
    base_dir = Path(__file__).resolve().parent
    xlsx_path = base_dir / "Master_Company_Email_Sheet (1).xlsx"
    out_path = base_dir / "recruiter_companies.json"

    with zipfile.ZipFile(xlsx_path) as z:
        ss_xml = ET.fromstring(z.read("xl/sharedStrings.xml"))
        strings = []
        for si in ss_xml.findall("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}si"):
            t = si.find("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}t")
            if t is not None and t.text:
                strings.append(t.text)
            else:
                r_texts = [
                    r.find("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}t").text
                    for r in si.findall("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}r")
                    if r.find("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}t") is not None
                ]
                strings.append("".join(filter(None, r_texts)))

        sheet_xml = ET.fromstring(z.read("xl/worksheets/sheet1.xml"))
        rows = []
        for row in sheet_xml.iter("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}row"):
            row_vals = {}
            for c in row.iter("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}c"):
                r_coord = c.attrib.get("r", "")
                col_letter = "".join([ch for ch in r_coord if ch.isalpha()])
                t_attr = c.attrib.get("t", "")
                v = c.find("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}v")
                val = v.text if v is not None else ""
                if t_attr == "s" and val.isdigit():
                    val = strings[int(val)]
                row_vals[col_letter] = val.strip() if isinstance(val, str) else ""
            if row_vals:
                rows.append(row_vals)

    company_map = defaultdict(list)
    for r in rows[1:]:
        comp = r.get("A", "").strip()
        email = r.get("B", "").strip().lower()
        if comp and email:
            if email not in company_map[comp]:
                company_map[comp].append(email)

    generic_prefixes = {
        "hr", "hiring", "talent", "careers", "career", "jobs", "recruit",
        "recruitment", "team", "info", "support", "contact", "future", "founders"
    }

    output_list = []
    for comp, emails in company_map.items():
        domains = set()
        has_individual = False
        has_shared = False

        for em in emails:
            parts = em.split("@")
            if len(parts) == 2:
                user_part, dom = parts[0], parts[1]
                domains.add(dom)
                if any(p in user_part for p in generic_prefixes):
                    has_shared = True
                else:
                    has_individual = True

        if has_individual and has_shared:
            category = "mixed"
        elif has_individual:
            category = "individual"
        else:
            category = "shared_inbox"

        output_list.append({
            "company": comp,
            "emails": emails,
            "email_type": category,
            "domains": sorted(list(domains)),
            "email_count": len(emails)
        })

    output_data = {
        "total_unique_companies": len(output_list),
        "total_emails": sum(len(x["emails"]) for x in output_list),
        "companies": output_list
    }

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2)

    print(f"Successfully wrote {len(output_list)} companies and {output_data['total_emails']} emails to {out_path}")

if __name__ == "__main__":
    extract_recruiter_data()
