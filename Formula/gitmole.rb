class Gitmole < Formula
  include Language::Python::Virtualenv

  desc "Offline git repository analysis with a terminal report"
  homepage "https://github.com/antvinni/gitmole"
  url "https://github.com/antvinni/gitmole/releases/download/v0.31.0/gitmole-0.31.0.tar.gz"
  sha256 "c3ded361a8282a2d0fa64346a7f05c7d0eb0602b0141b793928b7817133def8c"
  license "MIT"
  head "https://github.com/antvinni/gitmole.git", branch: "main"

  depends_on "python@3.14"

  # The tools gitmole runs, pinned to the versions gitmole/tools.py names and installed into
  # libexec/tools, which the gitmole wrapper puts first on PATH. One gitmole version is then one
  # toolchain: a newer betterleaks cannot change what counts as a secret under the same version line.
  # tests/test_tools.py holds the table and this file to each other. Moving a tool is its own release.
  TOOLS = %w[scc git-sizer betterleaks osv-scanner jscpd].freeze

  on_macos do
    on_arm do
      resource "scc" do
        url "https://github.com/boyter/scc/releases/download/v4.1.0/scc_Darwin_arm64.tar.gz"
        sha256 "7201c7aa4aace058d43308462cba72adb18f6094c08c0741727455976d0a0747"
      end
      resource "git-sizer" do
        url "https://github.com/github/git-sizer/releases/download/v1.5.0/git-sizer-1.5.0-darwin-arm64.zip"
        sha256 "7d1e8a6e1218d4640eebcca54c78b855055eb387eac34647b4928f072ffb8805"
      end
      resource "betterleaks" do
        url "https://github.com/betterleaks/betterleaks/releases/download/v1.8.1/betterleaks_1.8.1_darwin_arm64.tar.gz"
        sha256 "8e80f33b5f2a7426b390347b9fd466033723cb94b6bdffa7572632e2eaec964e"
      end
      resource "osv-scanner" do
        url "https://github.com/google/osv-scanner/releases/download/v2.6.0/osv-scanner_darwin_arm64"
        sha256 "98c460dcd37de25819babd757d04542045b6243113e209edcd4d89fedb0256b4"
      end
      resource "jscpd" do
        url "https://registry.npmjs.org/jscpd-darwin-arm64/-/jscpd-darwin-arm64-5.3.0.tgz"
        sha256 "003b73251d913ae7c34fb9b876afd9c677f17271c5e7fbfa63785d49de876c67"
      end
    end
    on_intel do
      resource "scc" do
        url "https://github.com/boyter/scc/releases/download/v4.1.0/scc_Darwin_x86_64.tar.gz"
        sha256 "7f705031228add7e55edded409179a60de6b538d41f153ba2922dee95adda50d"
      end
      resource "git-sizer" do
        url "https://github.com/github/git-sizer/releases/download/v1.5.0/git-sizer-1.5.0-darwin-amd64.zip"
        sha256 "f491edfb6e6552ecec401cd6a2b57b6790c9110b34286a01a0d315f65530de50"
      end
      resource "betterleaks" do
        url "https://github.com/betterleaks/betterleaks/releases/download/v1.8.1/betterleaks_1.8.1_darwin_x64.tar.gz"
        sha256 "6abc37df76f881cffae406aa2cec72bea6e6ae64b4e771b3ed21b4aac472ed10"
      end
      resource "osv-scanner" do
        url "https://github.com/google/osv-scanner/releases/download/v2.6.0/osv-scanner_darwin_amd64"
        sha256 "60c5296637e977b28eeda5c7f13573e447659a632922737f94d11fa7e30ad6ca"
      end
      resource "jscpd" do
        url "https://registry.npmjs.org/jscpd-darwin-x64/-/jscpd-darwin-x64-5.3.0.tgz"
        sha256 "71d114124c2b6f07ab236fc15cf733216cb4c82a95781d4aaef827bee324b77e"
      end
    end
  end

  on_linux do
    on_arm do
      # upstream publishes no Linux arm64 build of git-sizer, so this one platform builds it from the
      # pinned source: the version stays pinned everywhere.
      depends_on "go" => :build
      resource "scc" do
        url "https://github.com/boyter/scc/releases/download/v4.1.0/scc_Linux_arm64.tar.gz"
        sha256 "6e0d2a1f8d3540ba7df185477dec40bb7340f1b214bfd303147de5cad2bd7b8b"
      end
      resource "git-sizer" do
        url "https://github.com/github/git-sizer/archive/refs/tags/v1.5.0.tar.gz"
        sha256 "07a5ac5f30401a17d164a6be8d52d3d474ee9c3fb7f60fd83a617af9f7e902bb"
      end
      resource "betterleaks" do
        url "https://github.com/betterleaks/betterleaks/releases/download/v1.8.1/betterleaks_1.8.1_linux_arm64.tar.gz"
        sha256 "bbb578b12a2f65d7082ab436abf37724232bc71d8a078e3c41336574420f1b48"
      end
      resource "osv-scanner" do
        url "https://github.com/google/osv-scanner/releases/download/v2.6.0/osv-scanner_linux_arm64"
        sha256 "2c71403eb443d05891c4f268c3ad771cf4f16e5443463fd7851ef8f454d3c7e4"
      end
      resource "jscpd" do
        url "https://registry.npmjs.org/jscpd-linux-arm64-gnu/-/jscpd-linux-arm64-gnu-5.3.0.tgz"
        sha256 "3170585aa42977b07a146cbc4f57e9ab366c493aeff1b7ebf23b62140924e574"
      end
    end
    on_intel do
      resource "scc" do
        url "https://github.com/boyter/scc/releases/download/v4.1.0/scc_Linux_x86_64.tar.gz"
        sha256 "c7328436d3027f4357d3d7853f7dc3ac2bbcb4ca08f1adad91a27c593884079b"
      end
      resource "git-sizer" do
        url "https://github.com/github/git-sizer/releases/download/v1.5.0/git-sizer-1.5.0-linux-amd64.zip"
        sha256 "a166f7692a02ba68239cb014386f0263ec15525a36928784482644423aae2395"
      end
      resource "betterleaks" do
        url "https://github.com/betterleaks/betterleaks/releases/download/v1.8.1/betterleaks_1.8.1_linux_x64.tar.gz"
        sha256 "efa407244e1ea8e35f582b8a42becdeac08bdead04f68eb752adda722d583c2a"
      end
      resource "osv-scanner" do
        url "https://github.com/google/osv-scanner/releases/download/v2.6.0/osv-scanner_linux_amd64"
        sha256 "ca69b3d3cd08f889a49dc0a383122f71cc528b83803671df5fd874d97485b108"
      end
      resource "jscpd" do
        url "https://registry.npmjs.org/jscpd-linux-x64-gnu/-/jscpd-linux-x64-gnu-5.3.0.tgz"
        sha256 "86eb64a88bacd1c31497d9d7420eaf6f60c1302aa94a5a9c7b948daf74b94da3"
      end
    end
  end

  # The tree-sitter grammars, pinned like everything else: the structure step (nesting, debt markers, the
  # import graph) runs by default from 0.32.0, so these are ordinary dependencies rather than an extra.
  # Each builds its C parser from the sdist here; tree-sitter-php stops at 0.23.9, the last with an sdist.
  resource "tree-sitter" do
    url "https://files.pythonhosted.org/packages/f7/03/5600b84aff2e6c4fe80cfebb4063fe2f50299521befe5f6092ab8c082f4a/tree_sitter-0.26.0.tar.gz"
    sha256 "b40c219edccc4564530c96f8f1556f6202b37cda964d1cbd7bd2b7e68b40a245"
  end

  resource "tree-sitter-c" do
    url "https://files.pythonhosted.org/packages/a6/c9/3834f3d9278251aea7312274971bc4c45b17aec2490fd4b884d93bd7019a/tree_sitter_c-0.24.2.tar.gz"
    sha256 "1628584df0299b5a340aa63f8e67b6c97c91517f52fa7e7a4c557e40adb330a9"
  end

  resource "tree-sitter-c-sharp" do
    url "https://files.pythonhosted.org/packages/9f/fb/7e2962bc1901daf264e7ce263b168e0139304a5f8f66c9b2baf20e550f87/tree_sitter_c_sharp-0.23.5.tar.gz"
    sha256 "2635c7d5ec93e59f2e831b571bed99c4cc68a5d183a0994020aa769e1b990a71"
  end

  resource "tree-sitter-cpp" do
    url "https://files.pythonhosted.org/packages/20/2c/4dd63d705a8933543cad9b92ff31be849b164fec91a6eb63475ebc9ce668/tree_sitter_cpp-0.23.4.tar.gz"
    sha256 "6a59c4cebb1ad1dc2e8d586cf8a72b39d21b8108b7b139d089719e81a339e41d"
  end

  resource "tree-sitter-go" do
    url "https://files.pythonhosted.org/packages/01/05/727308adbbc79bcb1c92fc0ea10556a735f9d0f0a5435a18f59d40f7fd77/tree_sitter_go-0.25.0.tar.gz"
    sha256 "a7466e9b8d94dda94cae8d91629f26edb2d26166fd454d4831c3bf6dfa2e8d68"
  end

  resource "tree-sitter-java" do
    url "https://files.pythonhosted.org/packages/fa/dc/eb9c8f96304e5d8ae1663126d89967a622a80937ad2909903569ccb7ec8f/tree_sitter_java-0.23.5.tar.gz"
    sha256 "f5cd57b8f1270a7f0438878750d02ccc79421d45cca65ff284f1527e9ef02e38"
  end

  resource "tree-sitter-javascript" do
    url "https://files.pythonhosted.org/packages/59/e0/e63103c72a9d3dfd89a31e02e660263ad84b7438e5f44ee82e443e65bbde/tree_sitter_javascript-0.25.0.tar.gz"
    sha256 "329b5414874f0588a98f1c291f1b28138286617aa907746ffe55adfdcf963f38"
  end

  resource "tree-sitter-php" do
    url "https://files.pythonhosted.org/packages/82/80/8847524fa52db064c7743c230786a2a4f1bf15946f365baa863c43510d27/tree_sitter_php-0.23.9.tar.gz"
    sha256 "61189167e47dddf8b4186b590169a96e132580f7a883254b2e4dc74b0c628f68"
  end

  resource "tree-sitter-python" do
    url "https://files.pythonhosted.org/packages/b8/8b/c992ff0e768cb6768d5c96234579bf8842b3a633db641455d86dd30d5dac/tree_sitter_python-0.25.0.tar.gz"
    sha256 "b13e090f725f5b9c86aa455a268553c65cadf325471ad5b65cd29cac8a1a68ac"
  end

  resource "tree-sitter-ruby" do
    url "https://files.pythonhosted.org/packages/09/5b/6d24be4fde4743481bd8e3fd24b434870cb6612238c8544b71fe129ed850/tree_sitter_ruby-0.23.1.tar.gz"
    sha256 "886ed200bfd1f3ca7628bf1c9fefd42421bbdba70c627363abda67f662caa21e"
  end

  resource "tree-sitter-rust" do
    url "https://files.pythonhosted.org/packages/b7/87/75cbd22b927267d310f76cca1ab3c1d9d41035dfa3eb9cc95f96ee199440/tree_sitter_rust-0.24.2.tar.gz"
    sha256 "54fb02a5911e345308b405174465112479f56dc39e3f1e7744d7568595f00db9"
  end

  resource "tree-sitter-typescript" do
    url "https://files.pythonhosted.org/packages/1e/fc/bb52958f7e399250aee093751e9373a6311cadbe76b6e0d109b853757f35/tree_sitter_typescript-0.23.2.tar.gz"
    sha256 "7b167b5827c882261cb7a50dfa0fb567975f9b315e87ed87ad0a0a3aedb3834d"
  end
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
    venv = virtualenv_create(libexec, "python3.14")
    venv.pip_install resources.reject { |r| TOOLS.include?(r.name) }
    venv.pip_install buildpath # not pip_install_and_link: bin/gitmole is the wrapper written below

    # Each pinned tool is one executable at the root of its archive (jscpd's is under bin/, and Linux
    # arm64 has git-sizer's source instead of a build).
    tools = libexec/"tools"
    tools.mkpath
    TOOLS.each do |name|
      resource(name).stage do
        if File.exist?("go.mod")
          system "go", "build", "-trimpath", "-ldflags", "-s -w", "-o", tools/name, "."
        else
          found = Dir[name, "bin/#{name}", "#{name}_*"].find { |f| File.file?(f) }
          odie "#{name}: no executable in the resource" if found.nil?
          tools.install found => name
        end
      end
      chmod 0755, tools/name
    end

    # gitmole runs the tools by name, so the pinned ones come first on PATH. A tool the user installed
    # elsewhere is still found when this directory does not hold it.
    (bin/"gitmole").write_env_script libexec/"bin/gitmole", PATH: "#{tools}:$PATH"
  end

  test do
    assert_match "gitmole #{version}", shell_output("#{bin}/gitmole --version")
    system "git", "init", "-q", "repo"
    (testpath/"repo/a.py").write "x = 1\n"
    system "git", "-C", "repo", "add", "a.py"
    system "git", "-C", "repo", "-c", "user.name=t", "-c", "user.email=t@x", "commit", "-q", "-m", "one"
    output = shell_output("#{bin}/gitmole repo --out out --markdown - 2>/dev/null")
    assert_match "1 commits", output

    # the pinned toolchain is installed and is what the wrapper finds first (gitmole/tools.py)
    assert_match "4.1.0", shell_output("#{libexec}/tools/scc --version")
    assert_match "1.5.0", shell_output("#{libexec}/tools/git-sizer --version")
    assert_match "1.8.1", shell_output("#{libexec}/tools/betterleaks --version")
    assert_match "2.6.0", shell_output("#{libexec}/tools/osv-scanner --version")
    assert_match "5.3.0", shell_output("#{libexec}/tools/jscpd --version")

    # the structure step's grammars come with gitmole, so the step runs without anything else installed
    system libexec/"bin/python", "-c", "import tree_sitter, tree_sitter_python, tree_sitter_php"
  end
end
