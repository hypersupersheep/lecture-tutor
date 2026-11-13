# Compound interest

- [Pretest](#pretest)
- [Simple and compound interest](#simple-and-compound-interest)
- [Growth over n years](#growth-over-n-years)
- [Compounding frequency](#compounding-frequency)

How to read this note: what the lecturer said and the slides show, in lecture order; quotes are verbatim; (slide N) is the footer number, (mm:ss) the recording time.

## Pretest

<!-- tal:pretest -->
1. A friend claims that compound interest is just a higher rate than simple interest. Why is this wrong?

<details><summary>Answer</summary>

The rate can be the same; compounding changes what it applies to: the balance, which includes the interest already earned (slide 1, 0:36).

</details>

2. One account pays its quoted yearly rate in four instalments, another pays the same quoted rate in two. Which earns more over a full year, and why?

<details><summary>Answer</summary>

The one with four instalments: more payments a year give a higher effective annual rate, even with the same quoted rate (slide 3, 2:33).

</details>

3. A deposit of 500 earns 4% a year, compounded yearly. What does it hold after 4 years?

<details><summary>Answer</summary>

About 584.93: the balance is 500 times 1.04 to the power 4, the formula P(1 + r)^n with P = 500, r = 0.04 and n = 4 (slide 2, 1:12).

</details>
<!-- /tal:pretest -->

## Simple and compound interest

*(slide 1, 0:00–0:54)*

The lecturer starts from a bank that pays a yearly rate on a deposit (0:09). Slide 1 gives the two ways to pay it. Under simple interest "the rate applies to the deposit only"; under compound interest "the rate applies to the balance, past interest included" (slide 1).

The rate is the same in both; only its base differs. "Last year's interest is now part of the balance, and this year it earns interest too" (0:36), which the lecturer calls interest on interest. So compounding is not a higher rate but a base that grows every year by the interest already earned.

## Growth over n years

*(slide 2, 0:54–1:57)*

With deposit $P$ and yearly rate $r$, "after one year the balance is P times one plus r" (1:03). The next year multiplies that balance by $1+r$ again, and "every year is the same step" (1:12), so $n$ years give the formula of slide 2:
$$P(1+r)^n \tag{1}$$

On "a deposit of 100 at 5% a year" (1:21), simple interest adds 5 each year and holds 150 after 10 years (1:30), while equation (1) gives $100 \times 1.05^{10}$: "the same 100 grows to 162.89 after 10 years" (1:39). The gap widens "because each year starts from a bigger balance" (1:48). Reading (1) as $P(1+nr)$ brings back the simple 150.

<!-- tal:check -->
1. Why does the compound balance grow by a power of 1 + r rather than by equal steps each year?

<details><summary>Answer</summary>

Each year multiplies a bigger amount by the same 1 + r, because "last year's interest is now part of the balance" (0:36); equal steps would mean interest on the deposit only (slide 2, 1:03–1:21).

</details>
<!-- /tal:check -->

## Compounding frequency

*(slide 3, 1:57–2:58)*

Many accounts pay monthly or even daily (1:57). With a quoted rate $r$ paid $m$ times a year, "each payment uses r over m" (2:06), so "over a full year the balance grows by one plus r over m, to the power m" (2:15). "Take away one and you have the effective annual rate" (2:24):
$$(1+r/m)^m - 1 \tag{2}$$

More payments raise equation (2) "even with the same quoted rate" (2:33): four payments a year beat two. Hence the rule to "compare their effective annual rates, not the quoted ones" (2:42). The lecture ends by turning to what a future payment is worth now (2:51).

<!-- tal:check -->
1. You must rank three savings accounts that pay interest on different schedules. Which single number do you work out for each one?

<details><summary>Answer</summary>

Its effective annual rate, since quoted rates on different schedules cannot be compared directly (slide 3, 2:42).

</details>
<!-- /tal:check -->
