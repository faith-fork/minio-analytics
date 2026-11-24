from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
INDEX = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
APP = (ROOT / "app/static/app.js").read_text(encoding="utf-8")
PROMETHEUS = (ROOT / "app/static/prometheus-connections.js").read_text(encoding="utf-8")
BACKFILL = (ROOT / "app/static/backfill-jobs.js").read_text(encoding="utf-8")


class TestMasterConfigurationNavigation(unittest.TestCase):
    def test_master_configuration_replaces_separate_master_admin_links(self):
        self.assertIn('data-view="master-config"', INDEX)
        self.assertIn("Master Configuration", INDEX)
        self.assertNotIn('data-view="master-admin"', INDEX)
        self.assertNotIn('data-view="prometheus-connections"', INDEX)
        self.assertNotIn('data-view="backfill-jobs"', INDEX)

    def test_user_administration_remains_a_separate_admin_navigation_item(self):
        match = re.search(r'<button[^>]*data-view="users"[^>]*>', INDEX)
        self.assertIsNotNone(match)
        self.assertIn("admin-only", match.group(0))
        self.assertNotIn("master-admin-only", match.group(0))

    def test_master_configuration_exposes_the_three_agreed_tabs(self):
        for label in ("General Configuration", "Prometheus Configuration", "Historical Backfill"):
            self.assertIn(label, APP)
        for key in ('"general"', '"prometheus"', '"backfill"'):
            self.assertIn(key, APP)
        self.assertIn('role="tablist"', APP)
        self.assertIn('role="tabpanel"', APP)

    def test_existing_view_identifiers_route_to_the_matching_configuration_tab(self):
        self.assertIn('view==="master-admin"', APP)
        self.assertIn('view==="prometheus-connections"', APP)
        self.assertIn('view==="backfill-jobs"', APP)
        self.assertIn('state.masterConfigTab="general"', APP)
        self.assertIn('state.masterConfigTab="prometheus"', APP)
        self.assertIn('state.masterConfigTab="backfill"', APP)

    def test_set_view_uses_multi_element_selector_for_navigation_links(self):
        self.assertIn('$ (".nav-link").forEach'.replace(' ', ''), APP)
        self.assertNotIn('$(".nav-link").forEach', APP)

    def test_existing_configuration_renderers_are_reused(self):
        self.assertIn('await renderMasterAdmin()', APP)
        self.assertIn('await window.renderPrometheusConnections()', APP)
        self.assertIn('await window.renderBackfillJobs()', APP)
        self.assertIn('window.renderPrometheusConnections = render;', PROMETHEUS)
        self.assertIn('window.renderBackfillJobs=renderBackfillJobs;', BACKFILL)

    def test_existing_prometheus_and_backfill_api_contracts_are_unchanged(self):
        self.assertIn('/api/master-admin/prometheus-connections', PROMETHEUS)
        self.assertIn('/api/master-admin/backfill-jobs', BACKFILL)
        self.assertIn('/api/master-admin/settings', APP)
        self.assertIn('/api/master-admin/backups', APP)


if __name__ == "__main__":
    unittest.main()
