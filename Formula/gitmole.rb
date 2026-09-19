class Gitmole < Formula
  include Language::Python::Virtualenv

  desc "Offline git repository analysis with a terminal report"
  homepage "https://github.com/antvinni/gitmole"
  url "https://github.com/antvinni/gitmole/releases/download/v0.29.0/gitmole-0.29.0.tar.gz"
  sha256 "d8d30f202333c40c8d65fb218556026e184b0a62f1079b01130eeaddd4654786"
  license "MIT"
  head "https://github.com/antvinni/gitmole.git", branch: "main"

  depends_on "betterleaks"
  depends_on "git-sizer"
  depends_on "jscpd"
  depends_on "osv-scanner"
  depends_on "python@3.14"
  depends_on "scc"

  resource "lizard" do
    url "https://files.pythonhosted.org/packages/a5/c9/97837b967a1a6bb64acb0e1738e19a154393ae1a9a448b9958176be5b10a/lizard-1.24.0.tar.gz"
    sha256 "2e88a7af9d23a98d3f4a30767134361bd4b7dde02c410209c6c72732a43bbb65"
  end

  resource "markdown-it-py" do
    url "https://files.pythonhosted.org/packages/06/ff/7841249c247aa650a76b9ee4bbaeae59370dc8bfd2f6c01f3630c35eb134/markdown_it_py-4.2.0.tar.gz"
    sha256 "04a21681d6fbb623de53f6f364d352309d4094dd4194040a10fd51833e418d49"
  end

  resource "mdurl" do
    url "https://files.pythonhosted.org/packages/d6/54/cfe61301667036ec958cb99bd3efefba235e65cdeb9c84d24a8293ba1d90/mdurl-0.1.2.tar.gz"
    sha256 "bb413d29f5eea38f31dd4754dd7377d4465116fb207585f97bf925588687c1ba"
  end

  resource "pathspec" do
    url "https://files.pythonhosted.org/packages/5a/82/42f767fc1c1143d6fd36efb827202a2d997a375e160a71eb2888a925aac1/pathspec-1.1.1.tar.gz"
    sha256 "17db5ecd524104a120e173814c90367a96a98d07c45b2e10c2f3919fff91bf5a"
  end

  resource "pygments" do
    url "https://files.pythonhosted.org/packages/49/2e/ced460408999b33da6b31b0021b0f37d329e202d4169aeb164493778f25b/pygments-2.21.0.tar.gz"
    sha256 "610ca751c9bc2492b38eb9a38a7fbc93edbbb2d7182edaf34e66ae493dee5c8c"
  end

  resource "rich" do
    url "https://files.pythonhosted.org/packages/c0/8f/0722ca900cc807c13a6a0c696dacf35430f72e0ec571c4275d2371fca3e9/rich-15.0.0.tar.gz"
    sha256 "edd07a4824c6b40189fb7ac9bc4c52536e9780fbbfbddf6f1e2502c31b068c36"
  end

  def install
    virtualenv_install_with_resources
  end

  test do
    assert_match "gitmole #{version}", shell_output("#{bin}/gitmole --version")
    system "git", "init", "-q", "repo"
    (testpath/"repo/a.py").write "x = 1\n"
    system "git", "-C", "repo", "add", "a.py"
    system "git", "-C", "repo", "-c", "user.name=t", "-c", "user.email=t@x", "commit", "-q", "-m", "one"
    output = shell_output("#{bin}/gitmole repo --out out --markdown - 2>/dev/null")
    assert_match "1 commits", output
  end
end
