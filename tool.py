#!/usr/bin/env python
# Python 3
# LinkFinder - Kanka versiyonu
# Bu script, verdiğin domainin anasayfasındaki tüm .js dosyalarını bulup
# içlerinde gizli kalmış API veya endpoint linklerini çıkarır.

import os
os.environ["BROWSER"] = "open"
import re, sys, glob, html, argparse, jsbeautifier, webbrowser, subprocess, base64, ssl, xml.etree.ElementTree

from gzip import GzipFile
from string import Template

try:
    from StringIO import StringIO
    readBytesCustom = StringIO
except ImportError:
    from io import BytesIO
    readBytesCustom = BytesIO

try:
    from urllib.request import Request, urlopen
except ImportError:
    from urllib2 import Request, urlopen


# Aradığımız linklerin regex'i, baya kapsamlıdır, .js dosyalarında gezinti için optimize
regex_str = r"""
  (?:"|')
  (
    ((?:[a-zA-Z]{1,10}://|//)
    [^"'/]{1,}\.
    [a-zA-Z]{2,}[^"']{0,})
    |
    ((?:/|\.\./|\./)
    [^"'><,;| *()(%%$^/\\\[\]]
    [^"'><,;|()]{1,})
    |
    ([a-zA-Z0-9_\-/]{1,}/
    [a-zA-Z0-9_\-/.]{1,}
    \.(?:[a-zA-Z]{1,4}|action)
    (?:[\?|#][^"|']{0,}|))
    |
    ([a-zA-Z0-9_\-/]{1,}/
    [a-zA-Z0-9_\-/]{3,}
    (?:[\?|#][^"|']{0,}|))
    |
    ([a-zA-Z0-9_\-]{1,}
    \.(?:php|asp|aspx|jsp|json|
         action|html|js|txt|xml)
    (?:[\?|#][^"|']{0,}|))
  )
  (?:"|')
"""

context_delimiter_str = "\n"

def hata_ver(mesaj):
    # Hata mesajları ve çıkış
    print("Kullanım: python %s [Seçenekler] -h için yardım" % sys.argv[0])
    print("Hata: %s" % mesaj)
    sys.exit()

def girdi_al(input):
    # Girdi tipi belirleme ve işleme
    if input.startswith(('http://', 'https://', 'file://', 'ftp://', 'ftps://')):
        return [input]
    if input.startswith('view-source:'):
        return [input[12:]]
    if args.burp:
        jsdosyalar = []
        items = xml.etree.ElementTree.fromstring(open(args.input, "r").read())
        for item in items:
            jsdosyalar.append({"js":base64.b64decode(item.find('response').text).decode('utf-8',"replace"), "url":item.find('url').text})
        return jsdosyalar
    if "*" in input:
        paths = glob.glob(os.path.abspath(input))
        dosyalar = [p for p in paths if os.path.isfile(p)]
        for i, dosya in enumerate(dosyalar):
            dosyalar[i] = "file://%s" % dosya
        if len(dosyalar) == 0:
            hata_ver('Girilen wildcard hiçbir dosya ile eşleşmedi.')
        return dosyalar
    yol = "file://%s" % os.path.abspath(input)
    if os.path.exists(input):
        return [yol]
    else:
        hata_ver("Dosya bulunamadı, http/https unutulmuş olabilir.")

def istegi_gonder(url):
    # HTTP isteği gönderiyoruz, gzip destekli
    q = Request(url)
    q.add_header('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.36')
    q.add_header('Accept', 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8')
    q.add_header('Accept-Language', 'en-US,en;q=0.8')
    q.add_header('Accept-Encoding', 'gzip')
    q.add_header('Cookie', args.cookies)
    try:
        sslcontext = ssl.create_default_context()
        response = urlopen(q, timeout=args.timeout, context=sslcontext)
    except:
        sslcontext = ssl.create_default_context()
        response = urlopen(q, timeout=args.timeout, context=sslcontext)
    if response.info().get('Content-Encoding') == 'gzip':
        data = GzipFile(fileobj=readBytesCustom(response.read())).read()
    elif response.info().get('Content-Encoding') == 'deflate':
        data = response.read().read()
    else:
        data = response.read()
    return data.decode('utf-8', 'replace')

def context_bul(benzerlik_listesi, icerik, delimiter_ekle=0, delimiter="\n"):
    # Linkin bulunduğu satır veya çevresini getirir
    elemanlar = []
    for m in benzerlik_listesi:
        link_str = m[0]
        start = m[1]
        end = m[2]
        baslangic = start
        bitis = end
        delim_uzunluk = len(delimiter)
        icerik_uzunluk = len(icerik) - 1
        while icerik[baslangic] != delimiter and baslangic > 0:
            baslangic -= 1
        while icerik[bitis] != delimiter and bitis < icerik_uzunluk:
            bitis += 1
        if delimiter_ekle:
            ctx = icerik[baslangic:bitis]
        else:
            ctx = icerik[baslangic + delim_uzunluk:bitis]
        elemanlar.append({"link": link_str, "context": ctx})
    return elemanlar

def dosya_parcala(icerik, regex_str, mod=1, filtre_regex=None, tekrar_sil=1):
    # İçerikten linkleri çekiyoruz, tekrar edenleri kaldırıyoruz
    global context_delimiter_str
    if mod == 1:
        if len(icerik) > 1000000:
            icerik = icerik.replace(";",";\r\n").replace(",",",\r\n")
        else:
            icerik = jsbeautifier.beautify(icerik)
    regex = re.compile(regex_str, re.VERBOSE)
    if mod == 1:
        tum_eslesmeler = [(m.group(1), m.start(0), m.end(0)) for m in re.finditer(regex, icerik)]
        elemanlar = context_bul(tum_eslesmeler, icerik, context_delimiter_str=context_delimiter_str)
    else:
        elemanlar = [{"link": m.group(1)} for m in re.finditer(regex, icerik)]
    if tekrar_sil:
        link_set = set()
        temiz_liste = []
        for eleman in elemanlar:
            if eleman["link"] not in link_set:
                link_set.add(eleman["link"])
                temiz_liste.append(eleman)
        elemanlar = temiz_liste
    filtreli = []
    for eleman in elemanlar:
        if filtre_regex:
            if re.search(filtre_regex, eleman["link"]):
                filtreli.append(eleman)
        else:
            filtreli.append(eleman)
    return filtreli

def cli_yazdir(endpoints):
    # Komut satırına çıktı verir
    for endpoint in endpoints:
        print(html.escape(endpoint["link"]).encode('ascii', 'ignore').decode('utf8'))

def html_kaydet(html):
    # Sonuçları html dosyasına yazıp açar
    gizle = os.dup(1)
    os.close(1)
    os.open(os.devnull, os.O_RDWR)
    try:
        s = Template(open('%s/template.html' % sys.path[0], 'r').read())
        with open(args.output, "wb") as f:
            f.write(s.substitute(content=html).encode('utf8'))
        print("Sonuç dosyası: file://%s" % os.path.abspath(args.output))
        dosya = "file:///%s" % os.path.abspath(args.output)
        if sys.platform.startswith('linux'):
            subprocess.call(["xdg-open", dosya])
        else:
            webbrowser.open(dosya)
    except Exception as e:
        print("Çıktı kaydedilemedi: %s" % e)
    finally:
        os.dup2(gizle, 1)

def url_kontrol(url):
    # .js dosyası mı? node_modules veya jquery engelle
    engelliler = ["node_modules", "jquery.js"]
    if url[-3:] == ".js":
        for engel in engelliler:
            if engel in url:
                return False
        if url.startswith("//"):
            url = "https:" + url
        if not url.startswith("http"):
            if url.startswith("/"):
                url = args.input.rstrip("/") + url
            else:
                url = args.input.rstrip("/") + "/" + url
        return url
    return False

def js_bul(html_icerik, base_url):
    # Sayfadan .js linklerini toplar
    jsler = set()
    pattern = re.compile(r'src=[\'"]([^\'"]+\.js)[\'"]', re.IGNORECASE)
    for link in pattern.findall(html_icerik):
        if link.startswith("//"):
            link = "https:" + link
        elif link.startswith("/"):
            link = base_url.rstrip("/") + link
        elif not link.startswith("http"):
            link = base_url.rstrip("/") + "/" + link
        jsler.add(link)
    return jsler

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-d", "--domain", help="Domain verip anasayfadaki tüm .js dosyalarını tarar", action="store_true")
    parser.add_argument("-i", "--input", help="URL, dosya veya klasör. Klasör için wildcard kullanabilirsin (örn: '/*.js')", required=True)
    parser.add_argument("-o", "--output", help="Çıktı dosya yolu ve adı (default: output.html)", default="output.html")
    parser.add_argument("-r", "--regex", help="Bulunan linkleri filtrelemek için regex", default=None)
    parser.add_argument("-b", "--burp", help="Burp Suite dosyası ile kullanım", action="store_true")
    parser.add_argument("-c", "--cookies", help="Yetkili js dosyaları için cookie ekle", default="")
    parser.add_argument("-t", "--timeout", help="İstek zaman aşımı (saniye, default 10)", type=int, default=10)
    args = parser.parse_args()

    if args.input.endswith("/"):
        args.input = args.input[:-1]

    mode = 1
    if args.output == "cli":
        mode = 0

    girdiler = girdi_al(args.input)
    sonuc_html = ""

    if args.domain:
        base_url = args.input
        try:
            anasayfa = istegi_gonder(base_url)
        except Exception as e:
            hata_ver(f"Anasayfa alınamadı: {e}")
        jsdosyalari = js_bul(anasayfa, base_url)
        tum_endpoints = []
        for jsurl in jsdosyalari:
            try:
                jsicerik = istegi_gonder(jsurl)
                endpoints = dosya_parcala(jsicerik, regex_str, mode, args.regex)
                tum_endpoints.extend(endpoints)
                print(f"Taranan dosya: {jsurl}")
            except Exception as e:
                print(f"{jsurl} alınamadı veya parse edilemedi: {e}")
        # Tekrar edenleri temizle
        gorenler = set()
        temiz_endpoints = []
        for ep in tum_endpoints:
            if ep["link"] not in gorenler:
                gorenler.add(ep["link"])
                temiz_endpoints.append(ep)
        if args.output == "cli":
            cli_yazdir(temiz_endpoints)
        else:
            for ep in temiz_endpoints:
                link = html.escape(ep["link"])
                baslik = f"<div><a href='{link}' class='text'>{link}</a>"
                govde = f"<div class='container'>{html.escape(ep['context'])}</div></div>"
                sonuc_html += baslik + govde
            html_kaydet(sonuc_html)

    else:
        for url in girdiler:
            if not args.burp:
                try:
                    dosya = istegi_gonder(url)
                except Exception as e:
                    hata_ver(f"Geçersiz girdi veya SSL hatası: {e}")
            else:
                dosya = url['js']
                url = url['url']
            endpoints = dosya_parcala(dosya, regex_str, mode, args.regex)
            if args.output == "cli":
                cli_yazdir(endpoints)
            else:
                sonuc_html += f"<h1>Dosya: <a href='{html.escape(url)}' target='_blank' rel='nofollow noopener noreferrer'>{html.escape(url)}</a></h1>"
                for ep in endpoints:
                    link = html.escape(ep["link"])
                    baslik = f"<div><a href='{link}' class='text'>{link}"
                    govde = f"</a><div class='container'>{html.escape(ep['context'])}</div></div>"
                    govde = govde.replace(html.escape(ep["link"]), f"<span style='background-color:yellow'>{html.escape(ep['link'])}</span>")
                    sonuc_html += baslik + govde
        if args.output != "cli":
            html_kaydet(sonuc_html)
