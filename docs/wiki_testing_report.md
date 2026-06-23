# 🧪 QA Testing Report & Verification Board

This document serves as the official testing report for the Farmers Market Bot. It traces our testing efforts back to the core user stories and features developed this week.

## 1. Unit Tests & Integration Tests Summary

We have implemented automated test suites using Python's `unittest` framework.
- **Unit Tests (`tests/test_message_handler.py`)**: Tests isolated functions such as `_translate_to_khmer()` to ensure accurate translations of crop names and units without requiring a database connection.
- **Integration Tests (`tests/test_services.py`)**: Tests the caching mechanisms and database interactions within `market_service.py` and `price_service.py` to ensure high performance and data integrity.

*Status: All automated tests pass successfully in the CI/CD pipeline.*

---

## 2. Structural Blueprint (The QA Verification Board)

This table explicitly traces our End-to-End manual testing back to our User Stories.

| Test ID | User Story Reference | Input/Action Trigger | Expected Behavior | Actual Behavior | Status (Pass/Fail) |
|---------|-----------------------|----------------------|-------------------|-----------------|--------------------|
| **TC-01** | US-01: User Registration | User types text instead of a valid phone number during registration. | Bot rejects input, displays a polite error message, and retains the `WAIT_PHONE` state. | As expected. | **PASS** ✅ |
| **TC-02** | US-02: View Catalog | User clicks the `/view_catalog` command and clicks a crop button. | Bot displays a popup with the crop's description, quality standards, and unit in Khmer. | As expected. | **PASS** ✅ |
| **TC-03** | US-03: Live Market Prices | User clicks `/price` to fetch international commodity prices. | Bot returns the locally adjusted prices in Khmer within 1 second using the caching system. | As expected. | **PASS** ✅ |
| **TC-04** | US-04: Post a Crop for Sale | User types `/sell ស្វាយ, ប្រភេទ A, 50kg, 1500៛` | Bot parses the input correctly, saves it to the database, and displays a success message. | As expected. | **PASS** ✅ |
| **TC-05** | US-05: View Marketplace | User types `/market` to view retail listings. | Bot retrieves the latest 10 listings from the database, displaying seller names and phone numbers. | As expected. | **PASS** ✅ |
| **TC-06** | US-06: Weather Location | User clicks "ផ្ញើទីតាំងរបស់ខ្ញុំ" (Send My Location) button. | Bot successfully reads latitude/longitude and fetches the 7-day temperature & rainfall forecast. | As expected. | **PASS** ✅ |
| **TC-07** | US-07: Error Handling | User types an unknown command (e.g., `/hello`). | Bot replies gracefully, advising the user to use `/start` or listing available commands. | As expected. | **PASS** ✅ |

---

## 3. Test Codes Repository

The actual automated test scripts are committed to the GitHub repository under the `/tests` directory.

To run the tests locally:
```bash
python -m unittest discover tests/
```
