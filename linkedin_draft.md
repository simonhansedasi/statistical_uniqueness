# LinkedIn Post Draft — Statistical Uniqueness

---

Think you're one in a million?

I'm 1 in 1.5 quadrillion.

I built a small tool that intersects my demographic and life-path attributes — education, occupation, income, marital history, languages, veteran status, where I've lived — against US Census and BLS distributions, then multiplies the joint probability across my age cohort (US males 35–39, ~11 million people).

The result: the expected number of people in that cohort who share my full statistical profile is less than one.

The math is simple. The independence assumption is generous (correlated traits inflate the uniqueness estimate). The data is real.

But here's what I actually found interesting: the rarest thing about me isn't my education or career. It's that I speak Estonian. One in 11,111 people in the US does. Stack that on top of a niche occupation (1%), moving between states (2.8%), and a few other filters — and the cohort collapses fast.

You're probably unique too. The code is on GitHub — fork it, grab a free Census API key, and run it locally in about five minutes.

---

*Alternate shorter version:*

Think you're one in a million?

I ran the numbers on my demographic + life-path profile against US Census data. My combination of attributes has an expected 0 matches in my age cohort of 11 million Americans.

Probability: 1 in 1.5 quadrillion.

The rarest thing about me: I speak Estonian. One in 11,111 Americans does. Everything else — niche occupation, income bracket, life-path timing — narrows it down from there.

Built a small tool to measure this. Code is on GitHub — fork it, grab a free Census API key, and run it locally in about five minutes.
