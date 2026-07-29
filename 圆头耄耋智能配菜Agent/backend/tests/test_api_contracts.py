import importlib
import unittest


try:
    _MAIN = importlib.import_module("app.main")
    _MAIN_IMPORT_ERROR = None
except Exception as exc:
    _MAIN = None
    _MAIN_IMPORT_ERROR = exc


EXPECTED_JOB_ROUTES = {
    ("/api/ingredients/jobs", "post", "202"),
    ("/api/ingredients/jobs/{job_id}", "get", "200"),
    ("/api/plans/jobs", "post", "202"),
    ("/api/plans/jobs/{job_id}", "get", "200"),
    ("/api/plans/channel-swap-jobs/{job_id}", "get", "200"),
}

EXPECTED_CHANNEL_ROUTES = {
    ("/api/plans/{plan_id}", "GET"),
    ("/api/plans/channel-swaps", "POST"),
    ("/api/plans/channel-swap-jobs/{job_id}", "GET"),
}

LEGACY_REPLACEMENT_ROUTES = {
    "/api/plans/replace",
    "/api/plans/replacement-jobs",
    "/api/plans/replacement-jobs/{job_id}",
}


def load_main(test_case):
    if _MAIN_IMPORT_ERROR is not None:
        test_case.fail(
            "app.main must import cleanly: {}: {}".format(
                type(_MAIN_IMPORT_ERROR).__name__,
                _MAIN_IMPORT_ERROR,
            )
        )
    return _MAIN


class ApiOpenApiContractTest(unittest.TestCase):
    def test_main_imports_without_legacy_replacement_dependencies(self):
        main = load_main(self)
        self.assertIsNotNone(main.app)

    def test_channel_routes_are_fixed_and_legacy_routes_are_removed(self):
        main = load_main(self)
        routes = {
            (route.path, method)
            for route in main.app.routes
            for method in getattr(route, "methods", set())
        }
        for route in EXPECTED_CHANNEL_ROUTES:
            with self.subTest(route=route):
                self.assertIn(route, routes)
        paths = {path for path, _ in routes}
        self.assertTrue(paths.isdisjoint(LEGACY_REPLACEMENT_ROUTES))

    def test_app_and_openapi_versions_are_1_7_0(self):
        main = load_main(self)
        self.assertEqual(main.app.version, "1.7.0")
        self.assertEqual(main.app.openapi()["info"]["version"], "1.7.0")

    def test_all_job_routes_declare_json_response_models(self):
        main = load_main(self)
        schema = main.app.openapi()
        for path, method, status in EXPECTED_JOB_ROUTES:
            with self.subTest(path=path, method=method):
                response = schema["paths"][path][method]["responses"][status]
                model_schema = response["content"]["application/json"]["schema"]
                self.assertTrue(
                    "$ref" in model_schema or "anyOf" in model_schema,
                    model_schema,
                )

    def test_channel_mutations_declare_accepted_response_models(self):
        main = load_main(self)
        schema = main.app.openapi()
        path = "/api/plans/channel-swaps"
        response = schema["paths"][path]["post"]["responses"]["202"]
        model_schema = response["content"]["application/json"]["schema"]
        self.assertIn("$ref", model_schema)


if __name__ == "__main__":
    unittest.main()
