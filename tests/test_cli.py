from mvn_updates.cli import build_parser


def test_prereleases_ignored_by_default():
    args = build_parser().parse_args(["-p", "."])
    assert args.allow_prereleases is False


def test_allow_prereleases_optout():
    args = build_parser().parse_args(["-p", ".", "--allow-prereleases"])
    assert args.allow_prereleases is True


def test_stable_only_still_accepted_as_noop():
    # kept for backward compatibility; it is now the default behaviour
    args = build_parser().parse_args(["-p", ".", "--stable-only"])
    assert args.allow_prereleases is False


def test_vendor_forks_ignored_by_default():
    args = build_parser().parse_args(["-p", "."])
    assert args.allow_vendor_forks is False


def test_allow_vendor_forks_optout():
    args = build_parser().parse_args(["-p", ".", "--allow-vendor-forks"])
    assert args.allow_vendor_forks is True
