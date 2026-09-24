class Gitmole < Formula
  include Language::Python::Virtualenv

  desc "Offline git repository analysis with a terminal report"
  homepage "https://github.com/antvinni/gitmole"
  url "https://github.com/antvinni/gitmole/releases/download/v0.35.1/gitmole-0.35.1.tar.gz"
  sha256 "cf6284ec930dd3a3212963ac9baf8e923b06ab80c1b8cee21e72d207a42a19f2"
  license "MIT"
  head "https://github.com/antvinni/gitmole.git", branch: "main"

  depends_on "python@3.14"

  # The tools gitmole runs, pinned to the versions gitmole/tools.py names and installed into
  # libexec/tools, which the gitmole wrapper puts first on PATH. One gitmole version is then one
  # toolchain: a newer betterleaks cannot change what counts as a secret under the same version line.
  # tests/test_tools.py holds the table and this file to each other. Moving a tool is its own release.
  TOOLS = %w[scc git-sizer betterleaks osv-scanner jscpd].freeze
  GRAMMARS = %w[
    tree-sitter-c
    tree-sitter-c-sharp
    tree-sitter-cpp
    tree-sitter-go
    tree-sitter-java
    tree-sitter-javascript
    tree-sitter-php
    tree-sitter-python
    tree-sitter-ruby
    tree-sitter-rust
    tree-sitter-typescript
  ].freeze

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
      resource "tree-sitter-c" do
        url "https://files.pythonhosted.org/packages/c1/1c/1140db75e7e375cda3c68792a33826c4fd40b5b98c3259d93c75f6c8368f/tree_sitter_c-0.24.2-cp310-abi3-macosx_11_0_arm64.whl", using: :nounzip
        sha256 "97bc80a224d48215d4e6e6376bf30d114f4c317b8145ff1b02afe785d4ba7bdd"
      end
      resource "tree-sitter-c-sharp" do
        url "https://files.pythonhosted.org/packages/c8/13/593c8603f834eaf15082b81e079289fc9f062b4c0ab5b9489134084eec06/tree_sitter_c_sharp-0.23.5-cp310-abi3-macosx_11_0_arm64.whl", using: :nounzip
        sha256 "a75994a11f6fed3f5b8c36ad6a00e5dc43205bd912c43af3a2a54fdf649664eb"
      end
      resource "tree-sitter-cpp" do
        url "https://files.pythonhosted.org/packages/12/1c/0337c016bdc00a77a3326d12f10ee836401dd28f27db6fd5b7734bfb21ed/tree_sitter_cpp-0.23.4-cp39-abi3-macosx_11_0_arm64.whl", using: :nounzip
        sha256 "bc3c404d9f0cbd87951213a85440afbf4c31e718f8d907fa9ee12bea4b8d276f"
      end
      resource "tree-sitter-go" do
        url "https://files.pythonhosted.org/packages/32/16/dd4cb124b35e99239ab3624225da07d4cb8da4d8564ed81d03fcb3a6ba9f/tree_sitter_go-0.25.0-cp310-abi3-macosx_11_0_arm64.whl", using: :nounzip
        sha256 "503b81a2b4c31e302869a1de3a352ad0912ccab3df9ac9950197b0a9ceeabd8f"
      end
      resource "tree-sitter-java" do
        url "https://files.pythonhosted.org/packages/57/ef/6406b444e2a93bc72a04e802f4107e9ecf04b8de4a5528830726d210599c/tree_sitter_java-0.23.5-cp39-abi3-macosx_11_0_arm64.whl", using: :nounzip
        sha256 "24acd59c4720dedad80d548fe4237e43ef2b7a4e94c8549b0ca6e4c4d7bf6e69"
      end
      resource "tree-sitter-javascript" do
        url "https://files.pythonhosted.org/packages/b1/8f/6b4b2bc90d8ab3955856ce852cc9d1e82c81d7ab9646385f0e75ffd5b5d3/tree_sitter_javascript-0.25.0-cp310-abi3-macosx_11_0_arm64.whl", using: :nounzip
        sha256 "8264a996b8845cfce06965152a013b5d9cbb7d199bc3503e12b5682e62bb1de1"
      end
      resource "tree-sitter-php" do
        url "https://files.pythonhosted.org/packages/90/74/965ecf806fab19eab474072a096f26e6c542821f3e72db887a1438c94273/tree_sitter_php-0.23.9-cp39-abi3-macosx_11_0_arm64.whl", using: :nounzip
        sha256 "d2eb8a646edb30386203e66eb90e471052b016925b1d6d4d192221c53cca97af"
      end
      resource "tree-sitter-python" do
        url "https://files.pythonhosted.org/packages/e6/1d/60d8c2a0cc63d6ec4ba4e99ce61b802d2e39ef9db799bdf2a8f932a6cd4b/tree_sitter_python-0.25.0-cp310-abi3-macosx_11_0_arm64.whl", using: :nounzip
        sha256 "480c21dbd995b7fe44813e741d71fed10ba695e7caab627fb034e3828469d762"
      end
      resource "tree-sitter-ruby" do
        url "https://files.pythonhosted.org/packages/e7/38/c41ecf7692b8ecccd26861d3293a88150a4a52fc081abe60f837030d7315/tree_sitter_ruby-0.23.1-cp39-abi3-macosx_11_0_arm64.whl", using: :nounzip
        sha256 "aa4ee7433bd42fac22e2dad4a3c0f332292ecf482e610316828c711a0bb7f794"
      end
      resource "tree-sitter-rust" do
        url "https://files.pythonhosted.org/packages/78/2a/cf39f881a545360b5a86bb1accba1f4acc713daab01fb9edd35b6e84f473/tree_sitter_rust-0.24.2-cp39-abi3-macosx_11_0_arm64.whl", using: :nounzip
        sha256 "01a46622735498493f29f3e628a90de95c96a07bfbeb88996243eb986b1cee36"
      end
      resource "tree-sitter-typescript" do
        url "https://files.pythonhosted.org/packages/8f/2f/1f36fda564518d84593f2740d5905ac127d590baf5c5753cef2a88a89c15/tree_sitter_typescript-0.23.2-cp39-abi3-macosx_11_0_arm64.whl", using: :nounzip
        sha256 "c7cc1b0ff5d91bac863b0e38b1578d5505e718156c9db577c8baea2557f66de8"
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
      resource "tree-sitter-c" do
        url "https://files.pythonhosted.org/packages/28/c1/26ed17730ec2c17bedc1b673349e5e0a466c578e3eb0327c3b73cf52bf97/tree_sitter_c-0.24.2-cp310-abi3-macosx_10_9_x86_64.whl", using: :nounzip
        sha256 "4d4579a8b54f0a442f903d88d3304cab77cd5c2031d4015baa4f2f8e15d6dcb7"
      end
      resource "tree-sitter-c-sharp" do
        url "https://files.pythonhosted.org/packages/ec/c4/86d8d469400a856757a464a6ac01af97d8cdacbb595e62bdb98bf1e9db90/tree_sitter_c_sharp-0.23.5-cp310-abi3-macosx_10_9_x86_64.whl", using: :nounzip
        sha256 "61e1981cf21b09ee547b9c4c68e64fb4394325f8fc8d5f6d50d41471eba923ea"
      end
      resource "tree-sitter-cpp" do
        url "https://files.pythonhosted.org/packages/b6/ac/11d56670f7b048362db872ca866fd00ba2002a322ab179f047b7c0fb2910/tree_sitter_cpp-0.23.4-cp39-abi3-macosx_10_9_x86_64.whl", using: :nounzip
        sha256 "aacb1759f0efd9dbc25bd8ee88184a340483018869f75412d9c3bc32c039a520"
      end
      resource "tree-sitter-go" do
        url "https://files.pythonhosted.org/packages/ca/aa/0984707acc2b9bb461fe4a41e7e0fc5b2b1e245c32820f0c83b3c602957c/tree_sitter_go-0.25.0-cp310-abi3-macosx_10_9_x86_64.whl", using: :nounzip
        sha256 "b852993063a3429a443e7bd0aa376dd7dd329d595819fabf56ac4cf9d7257b54"
      end
      resource "tree-sitter-java" do
        url "https://files.pythonhosted.org/packages/67/21/b3399780b440e1567a11d384d0ebb1aea9b642d0d98becf30fa55c0e3a3b/tree_sitter_java-0.23.5-cp39-abi3-macosx_10_9_x86_64.whl", using: :nounzip
        sha256 "355ce0308672d6f7013ec913dee4a0613666f4cda9044a7824240d17f38209df"
      end
      resource "tree-sitter-javascript" do
        url "https://files.pythonhosted.org/packages/2c/df/5106ac250cd03661ebc3cc75da6b3d9f6800a3606393a0122eca58038104/tree_sitter_javascript-0.25.0-cp310-abi3-macosx_10_9_x86_64.whl", using: :nounzip
        sha256 "b70f887fb269d6e58c349d683f59fa647140c410cfe2bee44a883b20ec92e3dc"
      end
      resource "tree-sitter-php" do
        url "https://files.pythonhosted.org/packages/c1/d3/85610fe9f228a4449a1c073ab9549e9eb9ffe2157e7ec5130f4d8c6b8a98/tree_sitter_php-0.23.9-cp39-abi3-macosx_10_9_x86_64.whl", using: :nounzip
        sha256 "2ea92ee590c4f2a68efb8a2b39a8abeba79b10e36f0d356eddca8fc0b924a29b"
      end
      resource "tree-sitter-python" do
        url "https://files.pythonhosted.org/packages/cf/64/a4e503c78a4eb3ac46d8e72a29c1b1237fa85238d8e972b063e0751f5a94/tree_sitter_python-0.25.0-cp310-abi3-macosx_10_9_x86_64.whl", using: :nounzip
        sha256 "14a79a47ddef72f987d5a2c122d148a812169d7484ff5c75a3db9609d419f361"
      end
      resource "tree-sitter-ruby" do
        url "https://files.pythonhosted.org/packages/23/2e/2717b9451c712b60f833827a696baf29d8e50a0f7dccbf22a8d7006cc19e/tree_sitter_ruby-0.23.1-cp39-abi3-macosx_10_9_x86_64.whl", using: :nounzip
        sha256 "39f391322d2210843f07081182dbf00f8f69cfbfa4687b9575cac6d324bae443"
      end
      resource "tree-sitter-rust" do
        url "https://files.pythonhosted.org/packages/d0/24/2b2d33af5e27c84a4fde4e8cd2594bb4ab1e1cf48756a9f40dadc84956cc/tree_sitter_rust-0.24.2-cp39-abi3-macosx_10_9_x86_64.whl", using: :nounzip
        sha256 "3620cfd12340efa43082d45df76349ff511893a9c361da2f8d6d51e307020a59"
      end
      resource "tree-sitter-typescript" do
        url "https://files.pythonhosted.org/packages/28/95/4c00680866280e008e81dd621fd4d3f54aa3dad1b76b857a19da1b2cc426/tree_sitter_typescript-0.23.2-cp39-abi3-macosx_10_9_x86_64.whl", using: :nounzip
        sha256 "3cd752d70d8e5371fdac6a9a4df9d8924b63b6998d268586f7d374c9fba2a478"
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
      resource "tree-sitter-c" do
        url "https://files.pythonhosted.org/packages/87/78/47dc570e7aee6b0a1ecc2520b30639cc2b06003154c9ab0672d86bf720d5/tree_sitter_c-0.24.2-cp310-abi3-manylinux2014_aarch64.manylinux_2_17_aarch64.manylinux_2_28_aarch64.whl", using: :nounzip
        sha256 "c098bedcd5ac86ff93fa734d51d1dd86aed40fd5ed7d634c7af11380a0469969"
      end
      resource "tree-sitter-c-sharp" do
        url "https://files.pythonhosted.org/packages/0a/c8/e0f391e343f5424d0627e3b6886c77baeb1249a3f10986be00b0b64ecdab/tree_sitter_c_sharp-0.23.5-cp310-abi3-manylinux2014_aarch64.manylinux_2_17_aarch64.manylinux_2_28_aarch64.whl", using: :nounzip
        sha256 "3ea38fb095d85d360dc5a0bec2fa605e496228876f798c9e089d5f0e72bcef46"
      end
      resource "tree-sitter-cpp" do
        url "https://files.pythonhosted.org/packages/b3/7b/dd38c049b10ed7fda118b903a1d28a8b55a36b98c30606ef90e8f374c6de/tree_sitter_cpp-0.23.4-cp39-abi3-manylinux_2_17_aarch64.manylinux2014_aarch64.whl", using: :nounzip
        sha256 "ccc43ddf1279d5d5a4ef190373f4cb16522801bec4492bcd4754edf2aeba2b7b"
      end
      resource "tree-sitter-go" do
        url "https://files.pythonhosted.org/packages/26/21/d3d88a30ad007419b2c97b3baeeef7431407faf9f686195b6f1cad0aedf9/tree_sitter_go-0.25.0-cp310-abi3-manylinux2014_aarch64.manylinux_2_17_aarch64.manylinux_2_28_aarch64.whl", using: :nounzip
        sha256 "148255aca2f54b90d48c48a9dbb4c7faad6cad310a980b2c5a5a9822057ed145"
      end
      resource "tree-sitter-java" do
        url "https://files.pythonhosted.org/packages/4e/6c/74b1c150d4f69c291ab0b78d5dd1b59712559bbe7e7daf6d8466d483463f/tree_sitter_java-0.23.5-cp39-abi3-manylinux_2_17_aarch64.manylinux2014_aarch64.whl", using: :nounzip
        sha256 "9401e7271f0b333df39fc8a8336a0caf1b891d9a2b89ddee99fae66b794fc5b7"
      end
      resource "tree-sitter-javascript" do
        url "https://files.pythonhosted.org/packages/96/c8/97da3af4796495e46421e9344738addb3602fa6426ea695be3fcbadbee37/tree_sitter_javascript-0.25.0-cp310-abi3-manylinux2014_aarch64.manylinux_2_17_aarch64.manylinux_2_28_aarch64.whl", using: :nounzip
        sha256 "199d09985190852e0912da2b8d26c932159be314bc04952cf917ed0e4c633e6b"
      end
      resource "tree-sitter-php" do
        url "https://files.pythonhosted.org/packages/5f/85/861878e08c9c2c0de2b06bb97606809be29830d36e477f64b497b03cff7c/tree_sitter_php-0.23.9-cp39-abi3-manylinux_2_17_aarch64.manylinux2014_aarch64.whl", using: :nounzip
        sha256 "be0b6fd55838b0a6cb6faa767d8db4d43cb565922da17c699b6edb7657e7d06b"
      end
      resource "tree-sitter-python" do
        url "https://files.pythonhosted.org/packages/40/bd/bf4787f57e6b2860f3f1c8c62f045b39fb32d6bac4b53d7a9e66de968440/tree_sitter_python-0.25.0-cp310-abi3-manylinux2014_aarch64.manylinux_2_17_aarch64.manylinux_2_28_aarch64.whl", using: :nounzip
        sha256 "be71650ca2b93b6e9649e5d65c6811aad87a7614c8c1003246b303f6b150f61b"
      end
      resource "tree-sitter-ruby" do
        url "https://files.pythonhosted.org/packages/d8/01/14ef2d5107e6f42b64a400c3bbc3dd3b8fd24c3cef5306004ae03668f231/tree_sitter_ruby-0.23.1-cp39-abi3-manylinux_2_17_aarch64.manylinux2014_aarch64.whl", using: :nounzip
        sha256 "62b36813a56006b7569db7868f6b762caa3f4e419bd0f8cf9ccbb4abb1b6254c"
      end
      resource "tree-sitter-rust" do
        url "https://files.pythonhosted.org/packages/b5/f6/a5a146df5c0a5daea3ffcd5d7245775fe7f084357770d5a313dd6245ae78/tree_sitter_rust-0.24.2-cp39-abi3-manylinux2014_aarch64.manylinux_2_17_aarch64.manylinux_2_28_aarch64.whl", using: :nounzip
        sha256 "9d76d1208c3638b871236090759dfc13d478921320653a6c9da5336e7c58f65a"
      end
      resource "tree-sitter-typescript" do
        url "https://files.pythonhosted.org/packages/96/2d/975c2dad292aa9994f982eb0b69cc6fda0223e4b6c4ea714550477d8ec3a/tree_sitter_typescript-0.23.2-cp39-abi3-manylinux_2_17_aarch64.manylinux2014_aarch64.whl", using: :nounzip
        sha256 "4b1eed5b0b3a8134e86126b00b743d667ec27c63fc9de1b7bb23168803879e31"
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
      resource "tree-sitter-c" do
        url "https://files.pythonhosted.org/packages/e9/8c/0dfb88d726f8821d1c4c36042f092be974a800afd734307a595b8604190c/tree_sitter_c-0.24.2-cp310-abi3-manylinux1_x86_64.manylinux_2_28_x86_64.manylinux_2_5_x86_64.whl", using: :nounzip
        sha256 "5041ef67eb68ce6bc8bb0b1f8ef3a5585ce523dae0c7eec109ab0627dd75aede"
      end
      resource "tree-sitter-c-sharp" do
        url "https://files.pythonhosted.org/packages/41/5a/a8855cbb5bbab28adb29c2c7f0e7be5a9f1d21450c13b3c3e613190d9b8c/tree_sitter_c_sharp-0.23.5-cp310-abi3-manylinux1_x86_64.manylinux_2_28_x86_64.manylinux_2_5_x86_64.whl", using: :nounzip
        sha256 "aa88a780204cd153c4c1ae2d59c654cee1402212fa0d069823d6d34301587438"
      end
      resource "tree-sitter-cpp" do
        url "https://files.pythonhosted.org/packages/6a/4d/23e390234d2acd351f5563b1079c515d7c1fe13ddb7392cee543be74dda3/tree_sitter_cpp-0.23.4-cp39-abi3-manylinux_2_17_x86_64.manylinux2014_x86_64.whl", using: :nounzip
        sha256 "773d2cafc08bbc0f998687fa33f42f378c1a371cdb582870c4d13abb06092706"
      end
      resource "tree-sitter-go" do
        url "https://files.pythonhosted.org/packages/86/fb/b30d63a08044115d8b8bd196c6c2ab4325fb8db5757249a4ef0563966e2e/tree_sitter_go-0.25.0-cp310-abi3-manylinux1_x86_64.manylinux_2_28_x86_64.manylinux_2_5_x86_64.whl", using: :nounzip
        sha256 "04b3b3cb4aff18e74e28d49b716c6f24cb71ddfdd66768987e26e4d0fa812f74"
      end
      resource "tree-sitter-java" do
        url "https://files.pythonhosted.org/packages/29/09/e0d08f5c212062fd046db35c1015a2621c2631bc8b4aae5740d7adb276ad/tree_sitter_java-0.23.5-cp39-abi3-manylinux_2_5_x86_64.manylinux1_x86_64.manylinux_2_17_x86_64.manylinux2014_x86_64.whl", using: :nounzip
        sha256 "370b204b9500b847f6d0c5ad584045831cee69e9a3e4d878535d39e4a7e4c4f1"
      end
      resource "tree-sitter-javascript" do
        url "https://files.pythonhosted.org/packages/5f/c4/7da74ecdcd8a398f88bd003a87c65403b5fe0e958cdd43fbd5fd4a398fcf/tree_sitter_javascript-0.25.0-cp310-abi3-manylinux1_x86_64.manylinux_2_28_x86_64.manylinux_2_5_x86_64.whl", using: :nounzip
        sha256 "9dc04ba91fc8583344e57c1f1ed5b2c97ecaaf47480011b92fbeab8dda96db75"
      end
      resource "tree-sitter-php" do
        url "https://files.pythonhosted.org/packages/ff/d2/2e0cd7edd03f4a8037beb20ab2b1b517678f897d570744b4e922d0978047/tree_sitter_php-0.23.9-cp39-abi3-manylinux_2_17_x86_64.manylinux2014_x86_64.whl", using: :nounzip
        sha256 "98c78c46d33e434a5456bc128432d498d3acf7c5d088d0a90e9b0b2ab231eef8"
      end
      resource "tree-sitter-python" do
        url "https://files.pythonhosted.org/packages/aa/cb/d9b0b67d037922d60cbe0359e0c86457c2da721bc714381a63e2c8e35eba/tree_sitter_python-0.25.0-cp310-abi3-manylinux1_x86_64.manylinux_2_28_x86_64.manylinux_2_5_x86_64.whl", using: :nounzip
        sha256 "86f118e5eecad616ecdb81d171a36dde9bef5a0b21ed71ea9c3e390813c3baf5"
      end
      resource "tree-sitter-ruby" do
        url "https://files.pythonhosted.org/packages/23/dd/1171b5dd25da10f768732a20fb62d2e3ae66e3b42329351f2ce5bf723abb/tree_sitter_ruby-0.23.1-cp39-abi3-manylinux_2_17_x86_64.manylinux2014_x86_64.whl", using: :nounzip
        sha256 "f7bcd93972b4ca2803856d4fe0fbd04123ff29c4592bbb9f12a27528bd252341"
      end
      resource "tree-sitter-rust" do
        url "https://files.pythonhosted.org/packages/ca/45/a051bbd3045a61182dde25b93ae9a33d2677c935b16952283e12eaf46051/tree_sitter_rust-0.24.2-cp39-abi3-manylinux1_x86_64.manylinux_2_28_x86_64.manylinux_2_5_x86_64.whl", using: :nounzip
        sha256 "e033c5a93b57c88e0a835880de39fc802909ff69f57aaff6000211c196ea5190"
      end
      resource "tree-sitter-typescript" do
        url "https://files.pythonhosted.org/packages/49/d1/a71c36da6e2b8a4ed5e2970819b86ef13ba77ac40d9e333cb17df6a2c5db/tree_sitter_typescript-0.23.2-cp39-abi3-manylinux_2_5_x86_64.manylinux1_x86_64.manylinux_2_17_x86_64.manylinux2014_x86_64.whl", using: :nounzip
        sha256 "e96d36b85bcacdeb8ff5c2618d75593ef12ebaf1b4eace3477e2bdb2abb1752c"
      end
    end
  end

  # py-tree-sitter builds from its source archive; the grammars cannot. Six of the eleven publish sdists that
  # omit the generated tree_sitter/parser.h (cpp, java, php, ruby, rust, typescript), so every grammar comes
  # from its prebuilt abi3 wheel instead, one per platform and pinned by sha256, installed below from the
  # staged file. The versions are pyproject.toml's, and tests/test_tools.py holds the two together.
  resource "tree-sitter" do
    url "https://files.pythonhosted.org/packages/f7/03/5600b84aff2e6c4fe80cfebb4063fe2f50299521befe5f6092ab8c082f4a/tree_sitter-0.26.0.tar.gz"
    sha256 "b40c219edccc4564530c96f8f1556f6202b37cda964d1cbd7bd2b7e68b40a245"
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
    venv.pip_install resources.reject { |r| TOOLS.include?(r.name) || GRAMMARS.include?(r.name) }
    # the grammars are wheels, which pip_install would refuse (--no-binary :all:), so they go in as files
    GRAMMARS.each do |name|
      resource(name).stage do
        system libexec/"bin/python", "-m", "pip", "install", "--no-deps", "--no-index", Dir["*.whl"].first
      end
    end
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
