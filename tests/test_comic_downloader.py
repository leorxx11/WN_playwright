import pytest

from comic_downloader import is_ad_url


@pytest.mark.parametrize("url", [
    # 文件名哈希以 "ad" 结尾，曾被子串匹配误判为广告
    "//dl1.wn01.download/down/3499/08c0f308efb1dc4362afb4dcca94c2ad.zip?n=玩轉學姊 96-97話",
    "https://dl1.wn01.download/down/1/abc.zip?n=load.ads.txt",
    "/download-index-aid-349802.html",
    "https://www.wn10.cfd/download-index-aid-349802.html",
    "https://www.wn10.cfd/photos-index-aid-1.html",
    "https://reads.example.com/a.zip",
    "",
    None,
])
def test_download_links_are_not_ads(url):
    assert is_ad_url(url) is False


@pytest.mark.parametrize("url", [
    "https://ad.example.com/click",
    "https://ads.example.com/x",
    "//cdn.ads.example.net/x",
    "https://advertisement-host.com/x",
    "https://ib.adnxs.com/x",
    "https://tpc.googlesyndication.com/x",
    "https://doubleclick.net/x",
])
def test_ad_hosts_are_detected(url):
    assert is_ad_url(url) is True
