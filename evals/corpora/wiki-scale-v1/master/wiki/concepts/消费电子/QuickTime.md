---
title: QuickTime
type: concept
industry: 消费电子
as_of: '2026-07-27'
summary: QuickTime 是苹果公司开发的多媒体框架，支持多种数字视频、音频、动画和互动式全景影像格式。其技术包括媒体播放器、QuickTime 文件格式和软件开发工具。版本历史从
  1991 年的 1.0 到 2016 年的 7.7.9，后续有 QuickTime X。Windows 版已停止支持。
source_ids:
- S1
---

# QuickTime

## 概述

QuickTime 是由苹果公司开发的一种多媒体框架，能够处理许多数字视频、媒体段落、音效、文字、动画、音乐格式，以及互动式全景影像的数项类型。[S1]

QuickTime 技术拥有三种主要的元件：
1. 媒体播放器，苹果电脑在他自己的网站免费让人下载以及内建在他的电脑中。[S1]
2. QuickTime 文件格式——公开文件并且任何人都可以使用，不须权利金。[S1]
3. 软件开发工具可用于 Macintosh 平台。这些工具允许人们开发他们自己的软件来操作 QuickTime 以及其他媒体文件。这些对已注册开发人员是免费的（注册免费）。[S1]

## QuickTime 播放程式

苹果在 Mac OS 推出免费之官方媒体播放软件，名字为「QuickTime Player」（早期的版本简单地使用了「MoviePlayer」这个名称）。这个播放器也包含一些媒体编辑和媒体创作的特色，但是使用者必须从 Apple 购买序列号来打开这些功能，把这个播放器转变为 "QuickTime Pro"。[S1]

有些公司使用 QuickTime 来作为他们的软件，例如：
- 苹果电脑自己拥有的 iTunes 音乐播放器（设计为容易操控语音媒体）使用 QuickTime 来作为他的播放技术。[S1]
- 大英百科全书的 DVD 需要 QuickTime 来播放电影片段。[S1]

独立的 QuickTime 6（MPEG-4）播放器在很多操作系统都存在，FFmpeg 程序库甚至支援第三方授权给 Apple 的 Sorenson 影像压缩格式。[S1]

## QuickTime 专业版

QuickTime 专业版是付费版的苹果电脑 QuickTime 媒体播放器技术。他提供的特色，像是 MPEG-4（和 7.0 版的 H.264）制作，以及其他未包含在免费播放器中的特色，像是输出各种不同视频 codec 格式（像是动画，DV, mjpeg 等等），图形格式（Tiff, Pict, Jpeg），以及声音（Wav, Aiff）。[S1]

## QuickTime 文件格式

QuickTime 文件格式的扩展名为 .mov 或 .qt，互联网媒体类型为 video/quicktime，类型代码为 MooV，统一类型标识为 com.apple.quicktime-movie，开发者是苹果公司，格式类型为视频文件格式，作为容器包含音频、视频、文字。[S1]

### QuickTime 和 MPEG-4

于 1998 年 2 月 11 日，国际标准组织（ISO）认可 QuickTime 文件格式作为 MPEG-4 标准的基础。这个行动的支持者表示 QuickTime 提供一个好的 "生命周期" 格式，很适合做撷取、编辑、档案、散布、和播放（相对于简单以档案为串流资料方式的 MPEG-1 和 MPEG-2 而言，不适合作编辑之用）。在 2002 年开发者增加了 MPEG-4 的相容性到 QuickTime 6。然而，苹果电脑延迟这个版本的推出达到数个月之久，是因为 MPEG-4 授权本身的争议，要求提出的授权金会限制很多使用者和内容的提供者。在妥协之后，苹果电脑于 2002 年 7 月 15 日推出 QuickTime 6。[S1]

## 架构

- 针对影音加以编码（Encoding）与转码（transcoding）。[S1]
- 针对影音加以解码（Decoding），并传送解完码的资料流（decoded stream）到 graphics 或是 audio subsystem。Mac OS X 操作系统下，QuickTime 传送 video playback 到 Quartz Extreme（OpenGL）Compositor。[S1]
- 可以用外插（plug-in）方式支援其他的解码器（codecs）像是 DivX。[S1]

## 开发

设计者可以使用 C 程序语言或是 Java 语言来与软件开发套件来发展 Mac 的多媒体应用程序。[S1]

## 历史

### 1991～1998 年：从 1.x 到 2.x

苹果电脑于 1991 年 12 月 2 日释出第一个 QuickTime 的版本，作为 System 7 上的多媒体附加功能。QuickTime 的首席开发者布鲁斯·利克（Bruce Leak），于 1991 年 5 月的苹果全球开发者大会上做了第一次的公开展示。他在 Mac 上展示了苹果电脑有名的电视广告「1984」，在那时候是一种令人印象深刻的突破。微软的竞争技术－ Video for Windows—在 1992 年 11 月之前都还未出现。[S1]

第一个版本的 QuickTime 制定的基本架构，到现在基本上还存在未更改，包含多重电影轨道，可扩充的媒体形态支援，一种开放的文件格式，以及完整的编辑功能。原本的视频 codec 包含：Apple 视频 codec（也称 "Road Pizza"），适合普通现场动作影像；动画 codec，使用简单的 run-length 图形压缩方式，适合卡通形态的大区域颜色很适合；图形 codec，对于每一点 8 位元（8-bit-per-pixel）的影像最佳化，包含有抖动的图形。[S1]

苹果电脑在 1992 年后期发放了 Mac OS 的 1.5 版本。苹果电脑在 1994 年 2 月发布了 QuickTime 2.0 for Mac OS 版——这个是唯一的一个不免费的版本。在这个版本中加入了对音乐轨迹的支持，音乐轨迹相当于 MIDI 的数据，这个功能可以驱动 sound-synthesis 引擎自我创建于 QuickTime 中（使用的声音许可证来自 Roland），或者是任何外部的 MIDI 设备，因此创建出来的声音只占用一小部分的电影数据。在接下来的 2.1 和 2.5 版本中，QuickTime 继续免费。工程师改良了对音乐的支持并增加了 sprite 轨迹，这个功能可以实现创建复杂的动画，文件大小就只比静态的图片大一点。QuickTime 2.0 for Windows 发布于 1994 年 11 月。[S1]

### 1998～2001 年：版本 3.0 与 4.0

运行于 Mac OS 的 QuickTime 3.0 于 1998 年 3 月 30 日发行。其现有的功能是免费的，但如果要获得 Apple 所提供的具有更多特性的 QuickTime Player 和 Picture Viewer 程序，最终用户需要通过购买一个 QuickTime Pro 许可证来解除对软件的限制。QuickTime 3.0 增加了支持图像导入的组件，从而可以从 GIF、JPEG、TIFF 和其他文件格式中读取图像。而通过 FireWire 主要作为视频数据输出的视频输出组件同样增加了视觉效果，使程序员可以把 real-time 技术运用到视频轨道中。一些效果甚至可以响应用户的鼠标单击，就像是电影本身的交互支持一样。[S1]

苹果于 1999 年 6 月 10 日发行了 QuickTime 4.0 for Mac OS。它增加了图像导出组件，支持输出成与预导入者可以阅读的相同格式的非 GIF（或许是因为 LZW 许可）。它增加了 Sorenson codec 的第一个版本，并且支持串流媒体。QuickTime 4.1 于 2000 年伊始发布，增加了在 Mac OS 9 及后续版本中播放超过 2G 的电影；并且终止了对 68K Mac 的支持。用户获得了操作 QuickTime Player via AppleScript 的能力。[S1]

### 2001 年至今：版本 5.0 及后续

QuickTime 5.0 for Mac OS 于 2001 年 4 月 23 日出现。它增加了「面板」功能和多处理图像压缩支持。在这一版本中只有拥有 QuickTime Pro 许可证的用户才可以使用全萤幕模式，这一做法引起了争议，至今尚未解决。[S1]

### QuickTime 6.x

QuickTime 6 于 2002 年 7 月 15 日发布，支持 Mac OS 8.6～X 和 Windows，添加支持 MPEG-2、MPEG-4 及 AAC 多媒体格式。此后陆续发布多个子版本，增加对 3GPP、3GPP2、ALAC 等格式的支持，并逐渐停止对旧版 Windows 的支持。[S1]

### QuickTime 7.x

QuickTime 7 系列始于 2005 年，支持 Mac OS X 和 Windows。7.2 版本添加了对 Windows Vista 的支持，7.3 停止对 Flash 内容的支持，7.5 停止对 Mac OS X v10.3 以下系统的支持，7.7 添加了对 Windows 7 的支持。最终稳定版本为 7.7.9（2016 年 1 月 7 日），此后苹果停止对 Windows 系统的技术支持。[S1]

### QuickTime X

QuickTime X（读作 Quicktime Ten，当中的 "X" 是罗马数字的十）是下一世代的 QuickTime，在 2008 年 6 月 9 日的 WWDC 上发表。产品预期会在 2009 年的年中随同 Mac OS X v10.6 推出。Version X 会使用与 iOS 相同的媒体技术，并支援更新的编码及更具效益的媒体播放功能。[S1]

## 漏洞与错误

QuickTime 7.4 被发现会令 Adobe 出品的影像合成程式 After Effects 停止工作，因为这个版本的 QuickTime 开始加入了针对数字版权管理（DRM）支援的功能，让 QuickTime 可以播放通过 iTunes 租赁的电影。这个问题在 QuickTime 7.4.1 得到修正。[S1]

从 4.0 到 7.3 版本都潜藏有一个缓存溢出的错误，使安装了 QuickTime 播放器或 QuickTime 媒体串流客户端的电脑的保安存在漏洞。这个漏洞在 7.3.1 版解决了。此外，在 7.5.5 版之前的版本都存有跨网站指令码（XSS）的问题。[S1]

## 来源

- [S1] QuickTime - 维基百科，自由的百科全书 — https://zh.wikipedia.org/wiki/QuickTime（抓取日期：2026-07-27）
