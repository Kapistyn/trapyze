"""Where traPYze lives online. The release workflow fills in the real repository name."""

REPO = "kapistyn/trapyze"
HOME_PAGE = f"https://github.com/{REPO}"
RELEASES = f"{HOME_PAGE}/releases"
LATEST_API = f"https://api.github.com/repos/{REPO}/releases/latest"
INSTALL_PS1 = f"https://github.com/{REPO}/releases/latest/download/install.ps1"
SUPPORT = "https://www.buymeacoffee.com/kapistyn"
INSTALL_SH = f"https://github.com/{REPO}/releases/latest/download/install.sh"


def configured() -> bool:
    """False in a copy built from the source without a home online (then there's nothing to check)."""
    return not REPO.startswith("YOUR-GITHUB-NAME")
