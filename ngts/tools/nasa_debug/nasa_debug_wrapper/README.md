This wrapper plugin isolates the actual nasa_debug_plugin from autoloading and activating in
order to prevent the autouse of the unsupported fixtures that will fail and error the tests.
Only if the --nasa_debug option is provided the debug plugin activates.