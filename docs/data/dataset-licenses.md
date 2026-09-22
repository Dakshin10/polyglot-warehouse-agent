# Dataset Licenses

This document records the license for every external dataset incorporated into
the Nexora Technologies enterprise data platform. License compliance is a
first-class concern. All dataset files are excluded from the Git repository
(see `.gitignore`).

---

## AdventureWorks 2022

| Field | Value |
|---|---|
| **Dataset name** | AdventureWorks 2022 (Excel format) |
| **Kaggle source** | https://www.kaggle.com/datasets/tituspr/adventureworks2022-excel-format |
| **Original source** | Microsoft Corporation (sample database distributed with SQL Server) |
| **License** | Community Data License Agreement – Permissive – Version 1.0 (CDLA-Permissive-1.0) |
| **License URL** | https://cdla.dev/permissive-1-0/ |
| **Commercial use** | Permitted |
| **Redistribution** | Permitted with attribution |
| **Modification** | Permitted |
| **Kaggle provider** | tituspr |
| **Domain in Nexora** | Internal ERP (employees, HR, sales, procurement, production) |
| **Provenance note** | This dataset is a public sample database originally distributed by Microsoft. It does not represent actual company data. Nexora Technologies uses it as a simulated internal ERP source for demonstration and development purposes only. |

---

## Olist Brazilian E-Commerce Public Dataset

| Field | Value |
|---|---|
| **Dataset name** | Brazilian E-Commerce Public Dataset by Olist |
| **Kaggle source** | https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce |
| **Original source** | Olist (https://olist.com/) |
| **License** | Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International (CC BY-NC-SA 4.0) |
| **License URL** | https://creativecommons.org/licenses/by-nc-sa/4.0/ |
| **Commercial use** | **NOT PERMITTED** |
| **Redistribution** | Permitted with attribution and same license |
| **Modification** | Permitted with same license |
| **Attribution required** | Yes — cite Olist and the Kaggle dataset |
| **Kaggle provider** | olistbr |
| **Domain in Nexora** | External Marketplace Channel |
| **Provenance note** | This dataset was made publicly available by Olist and covers orders from 2016 to 2018 from the Brazilian marketplace. It does not represent Nexora Technologies' own business data. Nexora uses it as a simulated external marketplace source. This dataset must not be used for commercial purposes without explicit permission from Olist. |

> [!CAUTION]
> **CC BY-NC-SA 4.0 — Non-commercial use only.** This dataset may not be used
> in commercial products or services. It is used here for educational and
> research purposes only.

---

## Olist Marketing Funnel Dataset

| Field | Value |
|---|---|
| **Dataset name** | Marketing Funnel by Olist |
| **Kaggle source** | https://www.kaggle.com/datasets/olistbr/marketing-funnel-olist |
| **Original source** | Olist (https://olist.com/) |
| **License** | Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International (CC BY-NC-SA 4.0) |
| **License URL** | https://creativecommons.org/licenses/by-nc-sa/4.0/ |
| **Commercial use** | **NOT PERMITTED** |
| **Redistribution** | Permitted with attribution and same license |
| **Modification** | Permitted with same license |
| **Attribution required** | Yes — cite Olist and the Kaggle dataset |
| **Kaggle provider** | olistbr |
| **Domain in Nexora** | Marketplace Marketing Channel |
| **Cross-dataset link** | Links to Brazilian E-Commerce via `seller_id` |
| **Provenance note** | This dataset contains anonymized marketing leads and closed deals from Olist's seller acquisition process. Nexora uses it as a simulated marketing funnel source connected to the external marketplace channel. Non-commercial use only. |

> [!CAUTION]
> **CC BY-NC-SA 4.0 — Non-commercial use only.** Same license restriction as
> the Brazilian E-Commerce dataset above.

---

## License Summary Table

| Dataset | License | Commercial? | Redistribution |
|---|---|---|---|
| AdventureWorks 2022 | CDLA-Permissive-1.0 | ✅ Yes | ✅ With attribution |
| Olist Brazilian E-Commerce | CC BY-NC-SA 4.0 | ❌ No | ✅ With attribution + same license |
| Olist Marketing Funnel | CC BY-NC-SA 4.0 | ❌ No | ✅ With attribution + same license |

---

## Data Files and Git

All raw data files are excluded from the Git repository via `.gitignore`
patterns. Dataset checksums and metadata are recorded in `data/manifests/`.
Manifests ARE committed; data files are NOT.

To reproduce the data:
```bash
pwa ingest download  # or: python -m pwa.preprocessing.kaggle_download
```
