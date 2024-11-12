
def is_cur_test_has_marker(request, marker_name) -> bool:
    """
    check whether the current test has marker of the given marker name
    @param request: pytest request (default/builtin fixture)
    @param marker_name: name of the marker to check
    @return: True / False
    """
    return bool(request.node.get_closest_marker(marker_name))


def get_cur_test_param_value(request, param_name):
    """
    get the value of the given param name of a parametrized test

    if the test does not have parametrization of the given param_name, or if something else is not right, return None

    Example:
    if:
        the test has: @pytest.mark.parametrized('param_name', [1, 2, 3])
        current test is running on param_name = 2
        we call get_cur_test_param_value(request, 'param_name')
    the function should return 2
    """
    try:
        return request.node.callspec.params[param_name]
    except Exception:
        return None
