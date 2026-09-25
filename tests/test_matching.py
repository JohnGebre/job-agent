import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))
from scanner import Profile, score_job

P = Profile(
    ["Senior Power Platform Developer", "Power Platform Architect"],
    ["Maryland", "Virginia", "Washington, DC", "Remote - United States"],
    ["remote", "hybrid"],
    ["full-time", "contract"],
    80000, 50,
    ["Microsoft Power Platform", "Power Apps Canvas", "Power Automate", "Dataverse", "SharePoint", "Power BI", "Azure", "REST APIs"]
)

class MatchingTests(unittest.TestCase):
    def test_good_match(self):
        r = score_job({
            "title":"Senior Power Platform Developer", "location_text":"Remote - United States", "work_type":"remote", "employment_type":"full-time", "salary_min":120000,
            "description":"Microsoft Power Platform, Power Apps Canvas, Power Automate, Dataverse, SharePoint, Power BI, Azure, REST APIs", "requirements":""}, P)
        self.assertEqual(r["qualification_status"], "qualified")

    def test_bad_location(self):
        r = score_job({
            "title":"Power Platform Developer", "location_text":"Austin, TX", "work_type":"hybrid", "employment_type":"full-time", "salary_min":120000,
            "description":"Power Apps Canvas, Power Automate, Dataverse, SharePoint, Power BI", "requirements":""}, P)
        self.assertEqual(r["qualification_status"], "rejected")

if __name__ == "__main__":
    unittest.main()
