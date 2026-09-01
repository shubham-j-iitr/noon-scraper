import os
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("JOB_DATA_DIR", "/tmp/noon-scraper-test-jobs")


def _install_browser_stubs():
    selenium = types.ModuleType("selenium")
    webdriver = types.ModuleType("selenium.webdriver")
    webdriver.ChromeOptions = type("ChromeOptions", (), {"add_argument": lambda *a, **k: None})
    webdriver.Chrome = lambda *a, **k: None
    service = types.ModuleType("selenium.webdriver.chrome.service")
    service.Service = lambda *a, **k: None
    common = types.ModuleType("selenium.webdriver.common")
    by = types.ModuleType("selenium.webdriver.common.by")
    by.By = type("By", (), {"TAG_NAME": "tag", "CSS_SELECTOR": "css", "XPATH": "xpath", "NAME": "name"})
    keys = types.ModuleType("selenium.webdriver.common.keys")
    keys.Keys = type("Keys", (), {"ENTER": "ENTER", "ESCAPE": "ESCAPE"})
    action = types.ModuleType("selenium.webdriver.common.action_chains")
    action.ActionChains = object
    support = types.ModuleType("selenium.webdriver.support")
    ui = types.ModuleType("selenium.webdriver.support.ui")
    ui.WebDriverWait = object
    ec = types.ModuleType("selenium.webdriver.support.expected_conditions")
    ec.presence_of_element_located = lambda x: x
    exc = types.ModuleType("selenium.common.exceptions")
    for n in ["TimeoutException", "NoSuchElementException", "StaleElementReferenceException"]:
        setattr(exc, n, type(n, (Exception,), {}))

    modules = {
        "selenium": selenium,
        "selenium.webdriver": webdriver,
        "selenium.webdriver.chrome": types.ModuleType("selenium.webdriver.chrome"),
        "selenium.webdriver.chrome.service": service,
        "selenium.webdriver.common": common,
        "selenium.webdriver.common.by": by,
        "selenium.webdriver.common.keys": keys,
        "selenium.webdriver.common.action_chains": action,
        "selenium.webdriver.support": support,
        "selenium.webdriver.support.ui": ui,
        "selenium.webdriver.support.expected_conditions": ec,
        "selenium.common": types.ModuleType("selenium.common"),
        "selenium.common.exceptions": exc,
    }
    for name, mod in modules.items():
        sys.modules[name] = mod

    tenacity = types.ModuleType("tenacity")
    tenacity.retry = lambda *a, **k: (lambda f: f)
    tenacity.stop_after_attempt = lambda *a: None
    tenacity.wait_exponential = lambda *a, **k: None
    tenacity.retry_if_exception_type = lambda *a: None
    sys.modules["tenacity"] = tenacity

    filelock = types.ModuleType("filelock")
    filelock.FileLock = type("FileLock", (), {"__init__": lambda s, *a, **k: None})
    sys.modules["filelock"] = filelock


_install_browser_stubs()

from fastapi.testclient import TestClient
from api.main import app
from excel_exporter import ExcelExporter
from noon_scraper import build_noon_search_url, extract_noon_product_urls

client = TestClient(app)


def test_health_and_home():
    assert client.get("/health").json()["status"] == "ok"
    assert "Noon Product Scraper" in client.get("/").text


def test_excel_export(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    rows = [{
        "Search Keyword": "test", "Category": "Phones", "Title": "Demo",
        "Description": "x", "Price": "AED 1,234.50", "Rating": "4.5",
        "Reviews": "10", "Seller": "Demo Seller", "Grade": "A",
        "Delivery": "Express", "Product URL": "https://example.com/p/demo",
        "Region": "UAE", "Platform": "Noon"
    }]
    path = ExcelExporter().export_to_excel(rows)
    assert os.path.exists(path)


def test_noon_search_url():
    assert build_noon_search_url("iPhone 15", "uae") == "https://www.noon.com/uae-en/search/?q=iPhone+15"
    assert build_noon_search_url("iPhone 15", "ksa") == "https://www.noon.com/saudi-en/search/?q=iPhone+15"
    assert build_noon_search_url("Samsung S24 Ultra", "uae") == "https://www.noon.com/uae-en/search/?q=Samsung+S24+Ultra"


def test_noon_product_filtering():
    hrefs = [
        "https://www.noon.com/uae-en/example/p/N123/",
        "https://www.google.com/other",
        "https://www.noon.com/uae-en/example/p/N123/",
        "https://www.noon.com/uae-en/category/",
    ]
    assert extract_noon_product_urls(hrefs) == [hrefs[0]]


def test_validation():
    response = client.post("/api/jobs", json={
        "keywords": [], "region": "uae", "max_products": 5, "output": "excel"
    })
    assert response.status_code == 422


def test_google_sheets_rejected():
    response = client.post("/api/jobs", json={
        "keywords": ["iPhone 15"], "region": "uae", "max_products": 5,
        "headless": True, "output": "google_sheets"
    })
    assert response.status_code == 422
