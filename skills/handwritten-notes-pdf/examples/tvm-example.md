@tag FIN101 · S01 · 2026-10-06
# Time Value of Money  货币的时间价值
★ ① ==£1 今天 > £1 明年== —— 因为 利息 + 通胀
② 复利 = **利息的利息**（interest on interest）
$$FV_n = PV\,(1+r)^n$$ << 两年是 $(1+r)^2$，不是 $1+2r$！
③ 一年复利 $m$ 次：每次只给 $r/m$
$$FV_n = PV\left(1+\frac{r}{m}\right)^{nm}$$
例：£100，12%，每 4 个月一次 → $100\times1.04^3=£112.49$
> （单利 £112，多出的 £0.49 就是利息的利息）
::: 课堂讨论：AER vs gross
$\text{AER}=(1+g/m)^m-1$，$g=4.9\%,\ m=12 \Rightarrow 5.01\%\approx5\%$
⇒ 一年后是 ==£105==，不是 £104.9
> gross = 每期真正用的数；AER = 给人看的年化结果
:::
④ 连续复利：$m\to\infty$
$$\left(1+\frac{r}{m}\right)^{m}=e^{\,m\log(1+r/m)}\to e^{r}$$ << 洛必达
⇒ ++$FV = PV\,e^{rt}$++，$t$ 以年为单位，可以不是整数
> $r=5\%$：$m=1\to1.0500$，$m=12\to1.05116$，$m\to\infty\to1.05127$
★ !! 易错！月 → 年：$140\,e^{0.15\times0.5}$，不是 $0.15\times6$
⑤ 现值 = 倒过来**折现**
$$PV = FV_n(1+r)^{-n} = FV_n\left(1+\frac{r}{m}\right)^{-nm} = FV_n\,e^{-rn}$$
折现因子 < 1：==利率越高、时间越长 → 今天越不值钱==

> 自问：为什么一定是 gross < AER，不可能反过来？
