"""
Excel Ingestion Module
======================
Reads both Excel sheets and converts them to structured company data:
  1. "Top Product-Based Startups for Freshers.xlsx" — startup-specific with roles & openings
  2. "Master_Company_Email_Sheet (1).xlsx" — existing email contacts

Merges both datasets, deduplicates, and prepares for the enrichment pipeline.
"""
import zipfile
import xml.etree.ElementTree as ET
import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
from collections import defaultdict

logger = logging.getLogger(__name__)

NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


def _read_xlsx_raw(xlsx_path: Path) -> List[Dict[str, str]]:
    """
    Read an xlsx file using only the standard library (no openpyxl dependency).
    Returns rows as list of dicts with column-letter keys.
    """
    with zipfile.ZipFile(xlsx_path) as z:
        # Read shared strings
        ss_xml = ET.fromstring(z.read("xl/sharedStrings.xml"))
        strings = []
        for si in ss_xml.findall(f"{NS}si"):
            t = si.find(f"{NS}t")
            if t is not None and t.text:
                strings.append(t.text)
            else:
                # Rich text — concatenate runs
                r_texts = [
                    r.find(f"{NS}t").text
                    for r in si.findall(f"{NS}r")
                    if r.find(f"{NS}t") is not None
                ]
                strings.append("".join(filter(None, r_texts)))

        # Read sheet1
        sheet_xml = ET.fromstring(z.read("xl/worksheets/sheet1.xml"))
        rows = []
        for row in sheet_xml.iter(f"{NS}row"):
            row_vals = {}
            for c in row.iter(f"{NS}c"):
                r_coord = c.attrib.get("r", "")
                col_letter = "".join(ch for ch in r_coord if ch.isalpha())
                t_attr = c.attrib.get("t", "")
                v = c.find(f"{NS}v")
                val = v.text if v is not None else ""
                if t_attr == "s" and val.isdigit():
                    val = strings[int(val)]
                row_vals[col_letter] = val.strip() if isinstance(val, str) else ""
            if row_vals:
                rows.append(row_vals)

    return rows


def parse_freshers_xlsx(xlsx_path: Path) -> List[Dict[str, Any]]:
    """
    Parse "Top Product-Based Startups for Freshers.xlsx".
    Expected columns: A=Company Name, B=Industry, C=Fresher Roles,
                      D=Expected Opening Dates, E=Target Contact, F=Cold Email Sent?
    """
    rows = _read_xlsx_raw(xlsx_path)
    if not rows:
        return []

    # First row is header
    header = rows[0]
    logger.info(f"[Freshers XLSX] Headers: {header}")

    companies = []
    for r in rows[1:]:
        company_name = r.get("A", "").strip()
        if not company_name:
            continue
        companies.append({
            "company_name": company_name,
            "industry": r.get("B", "").strip(),
            "fresher_role": r.get("C", "").strip(),
            "opening_period": r.get("D", "").strip(),
            "target_contact_type": r.get("E", "").strip(),
            "cold_email_sent": r.get("F", "").strip().lower() in ("yes", "true", "y", "1"),
            "source_sheet": "freshers",
            "company_type": "startup",
        })

    logger.info(f"[Freshers XLSX] Parsed {len(companies)} companies")
    return companies


def parse_master_xlsx(xlsx_path: Path) -> List[Dict[str, Any]]:
    """
    Parse "Master_Company_Email_Sheet (1).xlsx".
    Expected columns: A=Company, B=Email
    """
    rows = _read_xlsx_raw(xlsx_path)
    if not rows:
        return []

    company_map = defaultdict(list)
    for r in rows[1:]:
        comp = r.get("A", "").strip()
        email = r.get("B", "").strip().lower()
        if comp and email:
            if email not in company_map[comp]:
                company_map[comp].append(email)

    companies = []
    for comp, emails in company_map.items():
        companies.append({
            "company_name": comp,
            "emails": emails,
            "source_sheet": "master",
        })

    logger.info(f"[Master XLSX] Parsed {len(companies)} companies with {sum(len(c['emails']) for c in companies)} emails")
    return companies


def merge_company_datasets(
    freshers_companies: List[Dict[str, Any]],
    master_companies: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Merge freshers and master datasets, deduplicating by company name.
    Freshers data takes priority for metadata (role, opening dates, etc.)
    Master data adds pre-existing emails.
    """
    # Build master lookup (case-insensitive)
    master_lookup = {}
    for mc in master_companies:
        key = mc["company_name"].strip().lower()
        master_lookup[key] = mc

    merged = []
    seen_companies = set()

    # Process freshers first (they have richer metadata)
    for fc in freshers_companies:
        key = fc["company_name"].strip().lower()
        seen_companies.add(key)

        entry = {**fc}
        # Merge in master emails if available
        if key in master_lookup:
            entry["existing_emails"] = master_lookup[key].get("emails", [])
        else:
            entry["existing_emails"] = []

        merged.append(entry)

    # Add master-only companies
    for mc in master_companies:
        key = mc["company_name"].strip().lower()
        if key not in seen_companies:
            seen_companies.add(key)
            merged.append({
                "company_name": mc["company_name"],
                "industry": "",
                "fresher_role": "",
                "opening_period": "",
                "target_contact_type": "",
                "cold_email_sent": False,
                "source_sheet": "master",
                "company_type": "",
                "existing_emails": mc.get("emails", []),
            })

    logger.info(f"[Merge] {len(merged)} unique companies "
                f"({len(freshers_companies)} from freshers, "
                f"{len(master_companies)} from master, "
                f"{len(merged) - len(freshers_companies)} master-only)")
    return merged


def load_all_companies(base_dir: Optional[Path] = None) -> List[Dict[str, Any]]:
    """
    Load and merge all company data from both Excel sheets.
    Returns a unified list ready for the enrichment pipeline.
    """
    if base_dir is None:
        base_dir = Path(__file__).resolve().parent.parent.parent.parent

    freshers_path = base_dir / "Top Product-Based Startups for Freshers.xlsx"
    master_path = base_dir / "Master_Company_Email_Sheet (1).xlsx"

    freshers = []
    if freshers_path.exists():
        freshers = parse_freshers_xlsx(freshers_path)
    else:
        logger.warning(f"[Load] Freshers xlsx not found: {freshers_path}")

    master = []
    if master_path.exists():
        master = parse_master_xlsx(master_path)
    else:
        logger.warning(f"[Load] Master xlsx not found: {master_path}")

    return merge_company_datasets(freshers, master)
