#!/usr/bin/env python3
"""北野工作所 リール用のBGM(さわやか・明るい職人系)を自前で作曲・合成して、mp4 に入れる。

既存の曲を使わず numpy で一から合成するので著作権の心配なし。
  music/bgm_a.wav  … Gメジャー 116BPM アコギのアルペジオ＋ベル(晴れた現場の朝)
  music/bgm_b.wav  … Cメジャー 104BPM マリンバ＋アコギ(やさしい・安心)
  music/bgm_c.wav  … Dメジャー 122BPM アコギのストローク寄り＋口笛風(軽快)
投稿ごとに番号で a→b→c と順番に使う(同じ曲が続かない)。

購入した曲(Audiostock など)を使うときは music/private/ に mp3/wav を置く。あればそちらを優先して使う
(複数あれば番号順に交代)。music/private/ は .gitignore 済み=公開リポジトリには上げない(再配布NGのため)。
完成した mp4 だけを push する。

使い方: python make_music.py                 # 曲を作る(music/ に無ければ)
        python make_music.py add 04_mune_tsumi  # 指定 mp4 の音を差し替える
        python make_music.py add-all          # posts/ の全 mp4 の音を差し替える
make_videos.py / make_flyer.py は動画を作った後に自動で add_music() を呼ぶ。
必要: numpy, ffmpeg
"""
import subprocess, sys, wave, zlib
from pathlib import Path
import numpy as np

HERE = Path(__file__).parent
POSTS = HERE / "posts"
MUSIC = HERE / "music"
PRIVATE = MUSIC / "private"   # 購入曲(公開しない)
SR = 44100
LEN = 48.0  # 秒(どの動画より長く作って切る)

NOTE = {"C": 0, "C#": 1, "D": 2, "D#": 3, "E": 4, "F": 5, "F#": 6, "G": 7, "G#": 8, "A": 9, "A#": 10, "B": 11}


def hz(name, octave):
    return 440.0 * 2 ** ((NOTE[name] + 12 * (octave + 1) - 69) / 12)


def chord_notes(root, minor=False):
    r = NOTE[root]
    third = 3 if minor else 4
    names = list(NOTE)
    return [names[r % 12], names[(r + third) % 12], names[(r + 7) % 12]]


rng = np.random.default_rng(7)


def env(n, a=0.005, d=0.3):
    t = np.arange(n) / SR
    e = np.exp(-t / d)
    na = max(1, int(a * SR))
    e[:na] *= np.linspace(0, 1, na)
    return e


def pluck(f, dur, bright=0.5, decay=0.996):
    """Karplus-Strong(アコギっぽい弦の音)。周期ごとにまとめて計算して速くする。"""
    n = int(dur * SR)
    p = max(2, int(SR / f))
    buf = rng.uniform(-1, 1, p)
    buf = np.convolve(buf, [bright, 1 - bright], mode="same")
    out = np.empty(n + p)
    out[:p] = buf
    k = p
    while k < n + p:
        prev = out[k - p:k]
        nxt = decay * 0.5 * (prev + np.roll(prev, 1))
        m = min(p, n + p - k)
        out[k:k + m] = nxt[:m]
        k += m
    y = out[p:p + n]
    return y * env(n, 0.002, dur * 0.6)


def bell(f, dur):
    n = int(dur * SR)
    t = np.arange(n) / SR
    y = np.sin(2 * np.pi * f * t) + 0.35 * np.sin(2 * np.pi * f * 2.0 * t) * np.exp(-t / 0.15) \
        + 0.15 * np.sin(2 * np.pi * f * 3.01 * t) * np.exp(-t / 0.08)
    return y * env(n, 0.003, 0.5)


def marimba(f, dur):
    n = int(dur * SR)
    t = np.arange(n) / SR
    y = np.sin(2 * np.pi * f * t) + 0.25 * np.sin(2 * np.pi * f * 4.0 * t) * np.exp(-t / 0.03)
    return y * env(n, 0.002, 0.28)


def whistle(f, dur):
    n = int(dur * SR)
    t = np.arange(n) / SR
    vib = 1 + 0.004 * np.sin(2 * np.pi * 5.5 * t) * np.clip(t / 0.2, 0, 1)
    ph = 2 * np.pi * np.cumsum(f * vib) / SR
    y = np.sin(ph) + 0.08 * np.sin(2 * ph)
    e = np.minimum(np.clip(t / 0.06, 0, 1), np.clip((dur - t) / 0.12, 0, 1))
    return y * e + rng.normal(0, 0.01, n) * e


def bass(f, dur):
    n = int(dur * SR)
    t = np.arange(n) / SR
    y = np.sin(2 * np.pi * f * t) + 0.3 * np.sin(2 * np.pi * 2 * f * t)
    e = np.minimum(np.clip(t / 0.01, 0, 1), np.exp(-t / 0.6)) * np.clip((dur - t) / 0.03, 0, 1)
    return y * e


def pad(freqs, dur):
    n = int(dur * SR)
    t = np.arange(n) / SR
    y = sum(np.sin(2 * np.pi * f * t) + 0.5 * np.sin(2 * np.pi * f * 1.003 * t) for f in freqs)
    e = np.minimum(np.clip(t / 0.4, 0, 1), np.clip((dur - t) / 0.4, 0, 1))
    return y * e / len(freqs)


def shaker(dur):
    n = int(dur * SR)
    x = rng.normal(0, 1, n)
    x = x - np.convolve(x, np.ones(6) / 6, mode="same")  # 高い音だけ残す
    return x * env(n, 0.004, 0.035)


def kick(dur=0.25):
    n = int(dur * SR)
    t = np.arange(n) / SR
    f = 50 + 70 * np.exp(-t / 0.03)
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / 0.12)


def clap(dur=0.2):
    n = int(dur * SR)
    x = rng.normal(0, 1, n)
    x = x - np.convolve(x, np.ones(12) / 12, mode="same")
    return x * env(n, 0.002, 0.06)


class Mix:
    def __init__(self):
        self.L = np.zeros(int(LEN * SR) + SR * 3)
        self.R = np.zeros_like(self.L)

    def add(self, sig, at, vol=1.0, pan=0.0):
        i = int(at * SR)
        if i >= len(self.L):
            return
        sig = sig[:len(self.L) - i] * vol
        self.L[i:i + len(sig)] += sig * np.sqrt((1 - pan) / 2)
        self.R[i:i + len(sig)] += sig * np.sqrt((1 + pan) / 2)

    def finish(self):
        st = np.stack([self.L, self.R])[:, :int(LEN * SR)]
        # かんたんな残響(遅らせた音を左右に少しずつ足す)
        wet = np.zeros_like(st)
        for ms, g in [(37, 0.35), (53, 0.3), (71, 0.25), (97, 0.2), (131, 0.15)]:
            d = int(ms * SR / 1000)
            wet[0, d:] += st[1, :-d] * g
            wet[1, d:] += st[0, :-d] * g
        st = st + 0.35 * wet
        st = np.tanh(st / (np.abs(st).max() + 1e-9) * 1.4)  # やわらかく潰して音量をそろえる
        st = st / np.abs(st).max() * 0.85
        return st


def song(key_oct, prog, bpm, lead, melody, guitar="arp", seed=1):
    global rng
    rng = np.random.default_rng(seed)
    m = Mix()
    beat = 60 / bpm
    bar = beat * 4
    nbars = int(LEN / bar) + 1
    for b in range(nbars):
        t0 = b * bar
        root, minor = prog[b % len(prog)]
        names = chord_notes(root, minor)
        oct_ = key_oct
        tones = [hz(names[0], oct_), hz(names[1], oct_), hz(names[2], oct_), hz(names[0], oct_ + 1)]
        intro = b < 1  # 最初の1小節はギターだけで始める
        # ギター
        if guitar == "arp":
            order = [0, 1, 2, 3, 2, 1, 2, 3]
            for i, k in enumerate(order):
                m.add(pluck(tones[k], beat * 1.6, 0.55), t0 + i * beat / 2 + rng.uniform(0, 0.006), 0.32, -0.35)
        else:  # ストローク(少しずつずらして弦を鳴らす)
            pattern = [0, 1.5, 2, 3, 3.5]
            for i, s in enumerate(pattern):
                up = i % 2 == 1
                seq = tones[::-1] if up else tones
                for j, f in enumerate(seq):
                    m.add(pluck(f, beat * 1.2, 0.6, 0.994), t0 + s * beat + j * 0.012, 0.2 if up else 0.26, -0.3 + 0.15 * j)
        m.add(pad([tones[0] / 2, tones[1] / 2, tones[2] / 2], bar), t0, 0.08, 0.2)
        if intro:
            continue
        # ベース
        broot = hz(names[0], oct_ - 2)
        for s, f in [(0, broot), (2, broot), (3, hz(names[2], oct_ - 2))]:
            m.add(bass(f, beat * (2 if s == 0 else 1) * 0.95), t0 + s * beat, 0.34)
        # リズム
        for i in range(8):
            m.add(shaker(0.12), t0 + i * beat / 2, 0.07 if i % 2 == 0 else 0.11, 0.4)
        m.add(kick(), t0, 0.35); m.add(kick(), t0 + 2 * beat, 0.3)
        m.add(clap(), t0 + beat, 0.12, -0.1); m.add(clap(), t0 + 3 * beat, 0.12, 0.1)
        # メロディ(2小節で1フレーズ、音名, 拍位置, 長さ)
        if b >= 2:
            phrase = melody[(b - 2) % len(melody)]
            for nm, o, s, d in phrase:
                m.add(lead(hz(nm, o), beat * d + 0.3), t0 + s * beat, 0.22, 0.25)
    return m.finish()


SONGS = {
    "a": dict(key_oct=3, prog=[("G", 0), ("D", 0), ("E", 1), ("C", 0)], bpm=116, lead=bell, seed=11,
              melody=[[("B", 5, 0, 1), ("D", 6, 1, 1), ("G", 5, 2, 1.5)],
                      [("A", 5, 0, 1), ("F#", 5, 1, 1), ("A", 5, 2, 1), ("D", 6, 3, 1)],
                      [("B", 5, 0, 1.5), ("G", 5, 1.5, 0.5), ("E", 5, 2, 2)],
                      [("C", 6, 0, 1), ("B", 5, 1, 1), ("G", 5, 2, 2)]]),
    "b": dict(key_oct=3, prog=[("C", 0), ("G", 0), ("A", 1), ("F", 0)], bpm=104, lead=marimba, seed=22,
              melody=[[("E", 5, 0, 0.5), ("G", 5, 0.5, 0.5), ("C", 6, 1, 1), ("G", 5, 2.5, 0.5), ("E", 5, 3, 1)],
                      [("D", 5, 0, 0.5), ("G", 5, 0.5, 0.5), ("B", 5, 1, 1), ("D", 6, 2, 2)],
                      [("C", 6, 0, 0.5), ("A", 5, 0.5, 0.5), ("E", 5, 1, 1), ("A", 5, 2.5, 0.5), ("C", 6, 3, 1)],
                      [("A", 5, 0, 0.5), ("F", 5, 0.5, 0.5), ("C", 5, 1, 1), ("G", 5, 2, 2)]]),
    "c": dict(key_oct=3, prog=[("D", 0), ("G", 0), ("B", 1), ("A", 0)], bpm=122, lead=whistle, guitar="strum", seed=33,
              melody=[[("F#", 5, 0, 1), ("A", 5, 1, 0.5), ("D", 6, 1.5, 1.5)],
                      [("B", 5, 0, 1), ("G", 5, 1, 1), ("D", 5, 2, 2)],
                      [("F#", 5, 0, 0.5), ("B", 5, 0.5, 1), ("A", 5, 1.5, 0.5), ("F#", 5, 2, 2)],
                      [("E", 5, 0, 1), ("C#", 5, 1, 1), ("A", 5, 2, 2)]]),
}


def write_wav(path, st):
    data = (st.T * 32767).astype("<i2").tobytes()
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR); w.writeframes(data)


def build(force=False):
    MUSIC.mkdir(exist_ok=True)
    for k, cfg in SONGS.items():
        p = MUSIC / f"bgm_{k}.wav"
        if p.exists() and not force:
            continue
        write_wav(p, song(**cfg))
        print("saved", p.name)


def pick(slug):
    """番号順に交代。番号が無い名前(flyer_…)は名前から決める。購入曲があればそちらを使う。"""
    head = slug.split("_", 1)[0]
    i = int(head) - 1 if head.isdigit() else zlib.crc32(slug.encode())
    bought = sorted(p for p in PRIVATE.glob("*") if p.suffix.lower() in (".mp3", ".wav", ".m4a")) if PRIVATE.exists() else []
    if bought:
        return bought[i % len(bought)]
    keys = sorted(SONGS)
    return MUSIC / f"bgm_{keys[i % len(keys)]}.wav"


def duration(mp4):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(mp4)],
                         capture_output=True, text=True, check=True).stdout
    return float(out.strip())


def add_music(mp4):
    """mp4 の映像はそのまま、音だけ BGM(最初0.3秒・最後1.5秒フェード)に差し替える。"""
    mp4 = Path(mp4)
    wav = pick(mp4.stem)
    if wav.parent == MUSIC:
        build()
    d = duration(mp4)
    tmp = mp4.with_suffix(".tmp.mp4")
    af = f"atrim=0:{d:.2f},afade=t=in:d=0.3,afade=t=out:st={max(0, d - 1.5):.2f}:d=1.5,loudnorm=I=-16:TP=-1.5"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(mp4), "-i", str(wav),
                    "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-af", af, "-ar", "44100",
                    "-c:a", "aac", "-b:a", "160k", "-t", f"{d:.2f}", "-movflags", "+faststart", str(tmp)], check=True)
    tmp.replace(mp4)
    print(f"music {mp4.name} <- {wav.name}  {d:.1f}秒")


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        build(force=True)
    elif args[0] == "add":
        for s in args[1:]:
            add_music(POSTS / f"{s}.mp4")
    elif args[0] == "add-all":
        for p in sorted(POSTS.glob("*.mp4")):
            add_music(p)
