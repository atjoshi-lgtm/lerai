import unittest

from lerai.overrides_pipeline.entity_extractor import _normalize_geographical_scope


class GeographicalScopeNormalizationTests(unittest.TestCase):
    def test_region_geo_name_is_mapped_to_code(self):
        geo_scope = {"Region-geo": ["North America"]}

        result = _normalize_geographical_scope(geo_scope)

        self.assertEqual(result["Region-geo"], ["NA"])

    def test_region_default_geo_code_is_coerced_to_region_geo(self):
        geo_scope = {"Region-default": ["NA"]}

        result = _normalize_geographical_scope(geo_scope)

        self.assertNotIn("Region-default", result)
        self.assertEqual(result["Region-geo"], ["NA"])

    def test_region_default_global_words_become_default(self):
        geo_scope = {"Region-default": ["global"]}

        result = _normalize_geographical_scope(geo_scope)

        self.assertEqual(result["Region-default"], ["default"])

    def test_region_metro_spaces_convert_to_underscores(self):
        geo_scope = {"Region-metro": ["New York", "San Francisco"]}

        result = _normalize_geographical_scope(geo_scope)

        self.assertEqual(result["Region-metro"], ["New_York", "San_Francisco"])


if __name__ == "__main__":
    unittest.main()
