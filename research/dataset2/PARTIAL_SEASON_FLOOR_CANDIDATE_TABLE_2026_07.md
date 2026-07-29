# Family #9 Full Threshold Candidate Table — 2026-07

Full compact threshold table, requested alongside
`PARTIAL_SEASON_RELIABILITY_PROPOSAL_2026_07.md`'s clarification of
the inclusion / participation-floor / meaningful-role-floor
distinction. Every row: exact threshold, metric, window (final-4/6/8),
team-game vs. active-game version, retained player-seasons, ADP-range
composition, era composition. Real data, `build_team_game_final_n_traits()`/
`build_active_game_final_n_traits()` plus the Source A/B opportunity
fields (targets/carries/attempts/`offense_snap_share`), base population
= players meeting the primary sample/participation floor
(`active_games≥4` for team-game, `games≥4` for active-game) for that
window and type -- i.e. every row here is ALREADY past the
participation floor; these candidate thresholds are being evaluated as
potential MEANINGFUL-ROLE flags on top of that, per the methodology
note in the main proposal doc (a meaningful-role threshold should
produce a separate role-status flag, not remove rows from the
underlying dataset). No threshold is selected. Era short codes:
pre-2011 / 2011-2020 / 2021+. ADP short codes: R1-2 / R3-5 / R6-10 /
R11+ / none (no real market ADP).

### final_4 -- team-game
| Pos | Metric | Threshold | Tier | Base n | Retained n (%) | Era (pre11/11-20/21+) | ADP (R1-2/R3-5/R6-10/R11+/none) |
|---|---|---|---|---|---|---|---|
| QB | attempts | >=15 | lenient | 486 | 483 (99.4%) | 124/257/102 | 21/54/136/77/195 |
| QB | attempts | >=40 | moderate | 486 | 483 (99.4%) | 124/257/102 | 21/54/136/77/195 |
| QB | attempts | >=60 | meaningful-role | 486 | 482 (99.2%) | 124/257/101 | 21/54/136/77/194 |
| QB | offense_snap_share | >=0.1 | lenient | 307 | 306 (99.7%) | 0/203/103 | 8/33/97/60/108 |
| QB | offense_snap_share | >=0.2 | moderate | 307 | 306 (99.7%) | 0/203/103 | 8/33/97/60/108 |
| QB | offense_snap_share | >=0.3 | meaningful-role | 307 | 305 (99.3%) | 0/203/102 | 8/33/97/60/107 |
| RB | carries | >=3 | lenient | 1118 | 1049 (93.8%) | 259/535/255 | 132/131/190/133/463 |
| RB | carries | >=8 | moderate | 1118 | 975 (87.2%) | 238/499/238 | 132/131/189/130/393 |
| RB | carries | >=15 | meaningful-role | 1118 | 844 (75.5%) | 214/432/198 | 132/124/173/115/300 |
| RB | offense_snap_share | >=0.1 | lenient | 719 | 662 (92.1%) | 0/413/249 | 89/91/126/94/262 |
| RB | offense_snap_share | >=0.2 | moderate | 719 | 591 (82.2%) | 0/373/218 | 89/90/120/87/205 |
| RB | offense_snap_share | >=0.3 | meaningful-role | 719 | 490 (68.2%) | 0/313/177 | 87/87/108/69/139 |
| WR | targets | >=2 | lenient | 1790 | 1470 (82.1%) | 170/904/396 | 99/162/231/166/812 |
| WR | targets | >=5 | moderate | 1790 | 1385 (77.4%) | 160/852/373 | 99/162/231/160/733 |
| WR | targets | >=8 | meaningful-role | 1790 | 1306 (73.0%) | 152/810/344 | 99/162/226/157/662 |
| WR | offense_snap_share | >=0.1 | lenient | 1175 | 1114 (94.8%) | 0/716/398 | 76/126/174/121/617 |
| WR | offense_snap_share | >=0.2 | moderate | 1175 | 1048 (89.2%) | 0/680/368 | 76/126/173/119/554 |
| WR | offense_snap_share | >=0.3 | meaningful-role | 1175 | 996 (84.8%) | 0/647/349 | 76/126/172/116/506 |
| TE | targets | >=2 | lenient | 721 | 641 (88.9%) | 74/387/180 | 6/35/76/76/448 |
| TE | targets | >=5 | moderate | 721 | 601 (83.4%) | 69/361/171 | 6/35/76/75/409 |
| TE | targets | >=8 | meaningful-role | 721 | 517 (71.7%) | 59/313/145 | 6/35/76/74/326 |
| TE | offense_snap_share | >=0.1 | lenient | 500 | 496 (99.2%) | 0/316/180 | 6/25/58/57/350 |
| TE | offense_snap_share | >=0.2 | moderate | 500 | 483 (96.6%) | 0/307/176 | 6/25/58/57/337 |
| TE | offense_snap_share | >=0.3 | meaningful-role | 500 | 463 (92.6%) | 0/297/166 | 6/25/58/57/317 |

### final_4 -- active-game
| Pos | Metric | Threshold | Tier | Base n | Retained n (%) | Era (pre11/11-20/21+) | ADP (R1-2/R3-5/R6-10/R11+/none) |
|---|---|---|---|---|---|---|---|
| QB | attempts | >=15 | lenient | 1059 | 999 (94.3%) | 256/469/274 | 32/75/187/159/546 |
| QB | attempts | >=40 | moderate | 1059 | 941 (88.9%) | 238/450/253 | 32/75/187/159/488 |
| QB | attempts | >=60 | meaningful-role | 1059 | 902 (85.2%) | 235/431/236 | 32/75/185/157/453 |
| QB | offense_snap_share | >=0.1 | lenient | 696 | 672 (96.6%) | 0/388/284 | 16/49/136/110/361 |
| QB | offense_snap_share | >=0.2 | moderate | 696 | 642 (92.2%) | 0/373/269 | 16/49/136/110/331 |
| QB | offense_snap_share | >=0.3 | meaningful-role | 696 | 625 (89.8%) | 0/364/261 | 16/49/136/110/314 |
| RB | carries | >=3 | lenient | 2430 | 2127 (87.5%) | 496/1072/559 | 227/233/352/252/1063 |
| RB | carries | >=8 | moderate | 2430 | 1861 (76.6%) | 427/941/493 | 227/232/342/233/827 |
| RB | carries | >=15 | meaningful-role | 2430 | 1534 (63.1%) | 359/779/396 | 226/223/315/202/568 |
| RB | offense_snap_share | >=0.1 | lenient | 1615 | 1363 (84.4%) | 0/831/532 | 153/165/249/170/626 |
| RB | offense_snap_share | >=0.2 | moderate | 1615 | 1095 (67.8%) | 0/668/427 | 153/158/228/145/411 |
| RB | offense_snap_share | >=0.3 | meaningful-role | 1615 | 844 (52.3%) | 0/524/320 | 150/148/188/106/252 |
| WR | targets | >=2 | lenient | 3678 | 2907 (79.0%) | 302/1703/902 | 150/259/383/286/1829 |
| WR | targets | >=5 | moderate | 3678 | 2622 (71.3%) | 277/1542/803 | 150/259/378/277/1558 |
| WR | targets | >=8 | meaningful-role | 3678 | 2311 (62.8%) | 248/1376/687 | 150/259/369/265/1268 |
| WR | offense_snap_share | >=0.1 | lenient | 2479 | 2246 (90.6%) | 0/1345/901 | 122/206/302/223/1393 |
| WR | offense_snap_share | >=0.2 | moderate | 2479 | 2030 (81.9%) | 0/1226/804 | 122/206/298/215/1189 |
| WR | offense_snap_share | >=0.3 | meaningful-role | 2479 | 1790 (72.2%) | 0/1085/705 | 122/205/290/206/967 |
| TE | targets | >=2 | lenient | 1959 | 1621 (82.7%) | 177/948/496 | 13/61/124/127/1296 |
| TE | targets | >=5 | moderate | 1959 | 1328 (67.8%) | 146/772/410 | 13/61/124/126/1004 |
| TE | targets | >=8 | meaningful-role | 1959 | 975 (49.8%) | 108/574/293 | 13/61/122/122/657 |
| TE | offense_snap_share | >=0.1 | lenient | 1322 | 1285 (97.2%) | 0/774/511 | 12/47/99/100/1027 |
| TE | offense_snap_share | >=0.2 | moderate | 1322 | 1186 (89.7%) | 0/717/469 | 12/47/99/100/928 |
| TE | offense_snap_share | >=0.3 | meaningful-role | 1322 | 1026 (77.6%) | 0/622/404 | 12/47/98/99/770 |

### final_6 -- team-game
| Pos | Metric | Threshold | Tier | Base n | Retained n (%) | Era (pre11/11-20/21+) | ADP (R1-2/R3-5/R6-10/R11+/none) |
|---|---|---|---|---|---|---|---|
| QB | attempts | >=15 | lenient | 649 | 639 (98.5%) | 163/318/158 | 29/63/160/107/280 |
| QB | attempts | >=40 | moderate | 649 | 632 (97.4%) | 161/315/156 | 29/63/160/107/273 |
| QB | attempts | >=60 | meaningful-role | 649 | 629 (96.9%) | 161/314/154 | 29/63/160/107/270 |
| QB | offense_snap_share | >=0.1 | lenient | 417 | 414 (99.3%) | 0/255/159 | 13/41/117/82/161 |
| QB | offense_snap_share | >=0.2 | moderate | 417 | 410 (98.3%) | 0/253/157 | 13/41/117/82/157 |
| QB | offense_snap_share | >=0.3 | meaningful-role | 417 | 408 (97.8%) | 0/252/156 | 13/41/117/82/155 |
| RB | carries | >=3 | lenient | 1633 | 1518 (93.0%) | 372/754/392 | 186/175/258/185/714 |
| RB | carries | >=8 | moderate | 1633 | 1407 (86.2%) | 345/699/363 | 186/174/255/175/617 |
| RB | carries | >=15 | meaningful-role | 1633 | 1247 (76.4%) | 308/620/319 | 185/174/247/160/481 |
| RB | offense_snap_share | >=0.1 | lenient | 1065 | 942 (88.5%) | 0/573/369 | 127/126/181/121/387 |
| RB | offense_snap_share | >=0.2 | moderate | 1065 | 791 (74.3%) | 0/487/304 | 126/123/171/108/263 |
| RB | offense_snap_share | >=0.3 | meaningful-role | 1065 | 633 (59.4%) | 0/396/237 | 125/118/146/80/164 |
| WR | targets | >=2 | lenient | 2572 | 2109 (82.0%) | 241/1236/632 | 129/211/307/230/1232 |
| WR | targets | >=5 | moderate | 2572 | 1966 (76.4%) | 223/1159/584 | 129/211/304/228/1094 |
| WR | targets | >=8 | meaningful-role | 2572 | 1835 (71.3%) | 209/1085/541 | 129/211/301/222/972 |
| WR | offense_snap_share | >=0.1 | lenient | 1694 | 1593 (94.0%) | 0/969/624 | 104/165/238/177/909 |
| WR | offense_snap_share | >=0.2 | moderate | 1694 | 1465 (86.5%) | 0/895/570 | 104/165/238/173/785 |
| WR | offense_snap_share | >=0.3 | meaningful-role | 1694 | 1337 (78.9%) | 0/821/516 | 104/165/234/167/667 |
| TE | targets | >=2 | lenient | 1257 | 1074 (85.4%) | 124/629/321 | 10/45/98/108/813 |
| TE | targets | >=5 | moderate | 1257 | 987 (78.5%) | 113/573/301 | 10/45/98/108/726 |
| TE | targets | >=8 | meaningful-role | 1257 | 835 (66.4%) | 92/492/251 | 10/45/98/108/574 |
| TE | offense_snap_share | >=0.1 | lenient | 843 | 832 (98.7%) | 0/509/323 | 10/35/77/82/628 |
| TE | offense_snap_share | >=0.2 | moderate | 843 | 799 (94.8%) | 0/488/311 | 10/35/77/82/595 |
| TE | offense_snap_share | >=0.3 | meaningful-role | 843 | 723 (85.8%) | 0/446/277 | 10/35/76/82/520 |

### final_6 -- active-game
| Pos | Metric | Threshold | Tier | Base n | Retained n (%) | Era (pre11/11-20/21+) | ADP (R1-2/R3-5/R6-10/R11+/none) |
|---|---|---|---|---|---|---|---|
| QB | attempts | >=15 | lenient | 1059 | 1007 (95.1%) | 258/472/277 | 32/75/187/160/553 |
| QB | attempts | >=40 | moderate | 1059 | 953 (90.0%) | 238/455/260 | 32/75/187/160/499 |
| QB | attempts | >=60 | meaningful-role | 1059 | 919 (86.8%) | 236/437/246 | 32/75/187/159/466 |
| QB | offense_snap_share | >=0.1 | lenient | 696 | 674 (96.8%) | 0/388/286 | 16/49/136/111/362 |
| QB | offense_snap_share | >=0.2 | moderate | 696 | 644 (92.5%) | 0/375/269 | 16/49/136/111/332 |
| QB | offense_snap_share | >=0.3 | meaningful-role | 696 | 620 (89.1%) | 0/361/259 | 16/49/136/111/308 |
| RB | carries | >=3 | lenient | 2430 | 2194 (90.3%) | 511/1106/577 | 227/233/355/256/1123 |
| RB | carries | >=8 | moderate | 2430 | 2004 (82.5%) | 465/1014/525 | 227/233/352/245/947 |
| RB | carries | >=15 | meaningful-role | 2430 | 1758 (72.3%) | 405/891/462 | 227/233/339/222/737 |
| RB | offense_snap_share | >=0.1 | lenient | 1615 | 1378 (85.3%) | 0/843/535 | 153/166/253/173/633 |
| RB | offense_snap_share | >=0.2 | moderate | 1615 | 1103 (68.3%) | 0/679/424 | 153/162/233/151/404 |
| RB | offense_snap_share | >=0.3 | meaningful-role | 1615 | 820 (50.8%) | 0/514/306 | 151/153/189/103/224 |
| WR | targets | >=2 | lenient | 3678 | 2973 (80.8%) | 305/1737/931 | 150/259/383/286/1895 |
| WR | targets | >=5 | moderate | 3678 | 2768 (75.3%) | 290/1622/856 | 150/259/380/285/1694 |
| WR | targets | >=8 | meaningful-role | 3678 | 2562 (69.7%) | 271/1511/780 | 150/259/378/277/1498 |
| WR | offense_snap_share | >=0.1 | lenient | 2479 | 2254 (90.9%) | 0/1351/903 | 122/206/302/223/1401 |
| WR | offense_snap_share | >=0.2 | moderate | 2479 | 2047 (82.6%) | 0/1230/817 | 122/206/301/219/1199 |
| WR | offense_snap_share | >=0.3 | meaningful-role | 2479 | 1800 (72.6%) | 0/1091/709 | 122/206/291/209/972 |
| TE | targets | >=2 | lenient | 1959 | 1658 (84.6%) | 181/969/508 | 13/61/124/127/1333 |
| TE | targets | >=5 | moderate | 1959 | 1491 (76.1%) | 166/863/462 | 13/61/124/127/1166 |
| TE | targets | >=8 | meaningful-role | 1959 | 1240 (63.3%) | 134/728/378 | 13/61/124/127/915 |
| TE | offense_snap_share | >=0.1 | lenient | 1322 | 1293 (97.8%) | 0/781/512 | 12/47/99/100/1035 |
| TE | offense_snap_share | >=0.2 | moderate | 1322 | 1189 (89.9%) | 0/721/468 | 12/47/99/100/931 |
| TE | offense_snap_share | >=0.3 | meaningful-role | 1322 | 1032 (78.1%) | 0/622/410 | 12/47/98/100/775 |

### final_8 -- team-game
| Pos | Metric | Threshold | Tier | Base n | Retained n (%) | Era (pre11/11-20/21+) | ADP (R1-2/R3-5/R6-10/R11+/none) |
|---|---|---|---|---|---|---|---|
| QB | attempts | >=15 | lenient | 749 | 726 (96.9%) | 194/349/183 | 29/65/168/122/342 |
| QB | attempts | >=40 | moderate | 749 | 711 (94.9%) | 190/344/177 | 29/65/168/122/327 |
| QB | attempts | >=60 | meaningful-role | 749 | 702 (93.7%) | 189/339/174 | 29/65/168/122/318 |
| QB | offense_snap_share | >=0.1 | lenient | 479 | 468 (97.7%) | 0/283/185 | 13/43/122/89/201 |
| QB | offense_snap_share | >=0.2 | moderate | 479 | 462 (96.5%) | 0/280/182 | 13/43/122/89/195 |
| QB | offense_snap_share | >=0.3 | meaningful-role | 479 | 457 (95.4%) | 0/277/180 | 13/43/122/89/190 |
| RB | carries | >=3 | lenient | 1890 | 1746 (92.4%) | 414/875/457 | 198/194/298/202/854 |
| RB | carries | >=8 | moderate | 1890 | 1612 (85.3%) | 382/811/419 | 198/193/296/195/730 |
| RB | carries | >=15 | meaningful-role | 1890 | 1443 (76.3%) | 338/731/374 | 198/193/285/181/586 |
| RB | offense_snap_share | >=0.1 | lenient | 1243 | 1066 (85.8%) | 0/644/422 | 133/141/208/134/450 |
| RB | offense_snap_share | >=0.2 | moderate | 1243 | 874 (70.3%) | 0/534/340 | 133/138/195/114/294 |
| RB | offense_snap_share | >=0.3 | meaningful-role | 1243 | 690 (55.5%) | 0/428/262 | 131/135/165/83/176 |
| WR | targets | >=2 | lenient | 2903 | 2383 (82.1%) | 271/1395/717 | 137/227/328/243/1448 |
| WR | targets | >=5 | moderate | 2903 | 2229 (76.8%) | 255/1312/662 | 137/227/325/243/1297 |
| WR | targets | >=8 | meaningful-role | 2903 | 2087 (71.9%) | 238/1236/613 | 137/227/322/237/1164 |
| WR | offense_snap_share | >=0.1 | lenient | 1917 | 1775 (92.6%) | 0/1073/702 | 111/177/253/189/1045 |
| WR | offense_snap_share | >=0.2 | moderate | 1917 | 1605 (83.7%) | 0/975/630 | 111/177/253/186/878 |
| WR | offense_snap_share | >=0.3 | meaningful-role | 1917 | 1446 (75.4%) | 0/881/565 | 111/177/248/180/730 |
| TE | targets | >=2 | lenient | 1515 | 1286 (84.9%) | 147/756/383 | 10/49/106/111/1010 |
| TE | targets | >=5 | moderate | 1515 | 1177 (77.7%) | 133/685/359 | 10/49/106/111/901 |
| TE | targets | >=8 | meaningful-role | 1515 | 1006 (66.4%) | 111/591/304 | 10/49/105/111/731 |
| TE | offense_snap_share | >=0.1 | lenient | 1010 | 993 (98.3%) | 0/605/388 | 10/39/84/85/775 |
| TE | offense_snap_share | >=0.2 | moderate | 1010 | 930 (92.1%) | 0/570/360 | 10/39/84/85/712 |
| TE | offense_snap_share | >=0.3 | meaningful-role | 1010 | 816 (80.8%) | 0/497/319 | 10/39/83/84/600 |

### final_8 -- active-game
| Pos | Metric | Threshold | Tier | Base n | Retained n (%) | Era (pre11/11-20/21+) | ADP (R1-2/R3-5/R6-10/R11+/none) |
|---|---|---|---|---|---|---|---|
| QB | attempts | >=15 | lenient | 1059 | 1009 (95.3%) | 259/473/277 | 32/75/187/160/555 |
| QB | attempts | >=40 | moderate | 1059 | 954 (90.1%) | 239/455/260 | 32/75/187/160/500 |
| QB | attempts | >=60 | meaningful-role | 1059 | 922 (87.1%) | 236/438/248 | 32/75/187/160/468 |
| QB | offense_snap_share | >=0.1 | lenient | 696 | 674 (96.8%) | 0/388/286 | 16/49/136/111/362 |
| QB | offense_snap_share | >=0.2 | moderate | 696 | 644 (92.5%) | 0/376/268 | 16/49/136/111/332 |
| QB | offense_snap_share | >=0.3 | meaningful-role | 696 | 621 (89.2%) | 0/362/259 | 16/49/136/111/309 |
| RB | carries | >=3 | lenient | 2430 | 2227 (91.6%) | 524/1121/582 | 227/234/356/257/1153 |
| RB | carries | >=8 | moderate | 2430 | 2061 (84.8%) | 484/1041/536 | 227/233/354/249/998 |
| RB | carries | >=15 | meaningful-role | 2430 | 1851 (76.2%) | 425/941/485 | 227/233/348/230/813 |
| RB | offense_snap_share | >=0.1 | lenient | 1615 | 1391 (86.1%) | 0/847/544 | 153/166/255/174/643 |
| RB | offense_snap_share | >=0.2 | moderate | 1615 | 1094 (67.7%) | 0/674/420 | 153/165/229/147/400 |
| RB | offense_snap_share | >=0.3 | meaningful-role | 1615 | 819 (50.7%) | 0/513/306 | 152/155/191/100/221 |
| WR | targets | >=2 | lenient | 3678 | 3002 (81.6%) | 310/1751/941 | 150/259/383/286/1924 |
| WR | targets | >=5 | moderate | 3678 | 2829 (76.9%) | 296/1658/875 | 150/259/381/285/1754 |
| WR | targets | >=8 | meaningful-role | 3678 | 2647 (72.0%) | 280/1554/813 | 150/259/379/280/1579 |
| WR | offense_snap_share | >=0.1 | lenient | 2479 | 2258 (91.1%) | 0/1355/903 | 122/206/302/224/1404 |
| WR | offense_snap_share | >=0.2 | moderate | 2479 | 2058 (83.0%) | 0/1236/822 | 122/206/299/221/1210 |
| WR | offense_snap_share | >=0.3 | meaningful-role | 2479 | 1832 (73.9%) | 0/1107/725 | 122/206/295/212/997 |
| TE | targets | >=2 | lenient | 1959 | 1663 (84.9%) | 181/972/510 | 13/61/124/127/1338 |
| TE | targets | >=5 | moderate | 1959 | 1533 (78.3%) | 173/890/470 | 13/61/124/127/1208 |
| TE | targets | >=8 | meaningful-role | 1959 | 1354 (69.1%) | 145/794/415 | 13/61/124/127/1029 |
| TE | offense_snap_share | >=0.1 | lenient | 1322 | 1293 (97.8%) | 0/781/512 | 12/47/99/100/1035 |
| TE | offense_snap_share | >=0.2 | moderate | 1322 | 1186 (89.7%) | 0/717/469 | 12/47/99/100/928 |
| TE | offense_snap_share | >=0.3 | meaningful-role | 1322 | 1028 (77.8%) | 0/615/413 | 12/47/99/100/770 |

