```json
[
  {
    "question_text": "A piece of wire of resistance \( R \) is cut into five equal parts. These parts are then connected in parallel. If the equivalent resistance of this combination is \( R' \), then the ratio \( \\frac{R}{R'} \\) is:\n\n(a) \( \\frac{1}{25} \\)\n\n(b) \( \\frac{1}{5} \\)\n\n(c) 5\n\n(d) 25",
    "type": "MCQ",
    "difficulty": "Medium",
    "options": ["\( \\frac{1}{25} \\)", "\( \\frac{1}{5} \\)", "5", "25"],
    "correct_answer": "25",
    "explanation": "When the wire is cut into five equal parts, each part has a resistance of \( R/5 \\). When connected in parallel, the equivalent resistance \( R' \\) is given by:\n\n\[ \\frac{1}{R'} = \\frac{1}{R/5} + \\frac{1}{R/5} + \\frac{1}{R/5} + \\frac{1}{R/5} + \\frac{1}{R/5} = \\frac{5}{R} \\times 5 = \\frac{25}{R} \\]\n\nThus, \( R' = \\frac{R}{25} \\). Therefore, the ratio \( \\frac{R}{R'} = \\frac{R}{R/25} = 25 \\). Hence, the correct answer is 25.",
    "topic": "Combination of resistors - Parallel",
    "bloom_level": "Apply"
  },
  {
    "question_text": "Which of the following terms does not represent electrical power in a circuit?\n\n(a) \( I²R \\)\n\n(b) \( IR² \\)\n\n(c) \( VI \\)\n\n(d) \( \\frac{V²}{R} \\)",
    "type": "MCQ",
    "difficulty": "Medium",
    "options": ["\( I²R \\)", "\( IR² \\)", "\( VI \\)", "\( \\frac{V²}{R} \\)"],
    "correct_answer": "\( IR² \\)",
    "explanation": "Electrical power in a circuit is given by \( P = VI = I²R = \\frac{V²}{R} \\). The term \( IR² \\) does not correspond to the standard expressions for electrical power. Therefore, option (b) \( IR² \\) does not represent electrical power.",
    "topic": "Electrical Power",
    "bloom_level": "Understand"
  },
  {
    "question_text": "An electric bulb is rated 220 V and 100 W. When it is operated on 110 V, the power consumed will be:\n\n(a) 100 W\n\n(b) 75 W\n\n(c) 50 W\n\n(d) 25 W",
    "type": "MCQ",
    "difficulty": "Medium",
    "options": ["100 W", "75 W", "50 W", "25 W"],
    "correct_answer": "25 W",
    "explanation": "The power consumed by a bulb is given by \( P = \\frac{V²}{R} \\). First, find the resistance of the bulb:\n\nAt rated condition: \( 100 = \\frac{220²}{R} \\Rightarrow R = \\frac{220²}{100} = 484 \\Omega \\).\n\nWhen operated at 110 V:\n\n\( P' = \\frac{110²}{484} = \\frac{12100}{484} = 25 \\text{ W} \\).\n\nTherefore, the correct answer is 25 W.",
    "topic": "Electrical Power - Voltage and Power Relationship",
    "bloom_level": "Apply"
  },
  {
    "question_text": "Two conducting wires of the same material and of equal lengths and equal diameters are first connected in series and then parallel in a circuit across the same potential difference. The ratio of heat produced in series and parallel combinations would be:\n\n(a) 1:2\n\n(b) 2:1\n\n(c) 1:4\n\n(d) 4:1",
    "type": "MCQ",
    "difficulty": "Medium",
    "options": ["1:2", "2:1", "1:4", "4:1"],
    "correct_answer": "1:4",
    "explanation": "When two identical resistors are connected in series, the total resistance \( R_s = 2R \\). When connected in parallel, the total resistance \( R_p = \\frac{R}{2} \\).\n\nHeat produced is proportional to Power \( P = \\frac{V^2}{R} \\). Thus:\n\n- Power in series: \( P_s = \\frac{V^2}{2R} \\)\n- Power in parallel: \( P_p = \\frac{V^2}{R/2} = \\frac{2V^2}{R} \\)\n\nTherefore, the ratio \( P_s : P_p = \\frac{V^2}{2R} : \\frac{2V^2}{R} = 1:4 \\).\n\nHence, the correct answer is 1:4.",
    "topic": "Heat Produced in Series and Parallel Resistors",
    "bloom_level": "Analyze"
  },
  {
    "question_text": "How is a voltmeter connected in the circuit to measure the potential difference between two points?",
    "type": "Short Answer",
    "difficulty": "Easy",
    "options": null,
    "correct_answer": "A voltmeter is connected in parallel across the two points between which the potential difference is to be measured.",
    "explanation": "A voltmeter needs to measure the potential difference without significantly affecting the circuit. Therefore, it is connected in parallel across the two points. Connecting in parallel ensures that the voltmeter experiences the same potential difference as the component across which it is connected.",
    "topic": "Measurement of Potential Difference",
    "bloom_level": "Understand"
  },
  {
    "question_text": "A copper wire has a diameter of 0.5 mm and a resistivity of \( 1.6 × 10^{-8} \) Ω m. What will be the length of this wire to make its resistance 10 Ω? How much does the resistance change if the diameter is doubled?",
    "type": "Numerical",
    "difficulty": "Hard",
    "options": null,
    "correct_answer": "The length of the wire should be approximately 122.72 meters. If the diameter is doubled, the resistance decreases to 2.5 Ω.",
    "explanation": "First, calculate the area of the wire.\n\nDiameter, \( d = 0.5 \) mm = \( 0.5 × 10^{-3} \) m.\n\nArea, \( A = \\frac{\\pi d^2}{4} = \\frac{\\pi (0.5 × 10^{-3})^2}{4} = \\frac{\\pi × 0.25 × 10^{-6}}{4} = \\frac{\\pi × 6.25 × 10^{-8}}{1} ≈ 1.9635 × 10^{-7} \) m².\n\nUsing the formula \( R = \\rho \\frac{l}{A} \\),\n\nRearranged to find length \( l = \\frac{R A}{\\rho} = \\frac{10 × 1.9635 × 10^{-7}}{1.6 × 10^{-8}} = \\frac{19.635 × 10^{-7}}{1.6 × 10^{-8}} ≈ 122.72 \) meters.\n\nIf the diameter is doubled to 1.0 mm,\n\nNew area, \( A' = \\frac{\\pi (1.0 × 10^{-3})^2}{4} = \\frac{\\pi × 1 × 10^{-6}}{4} = \\frac{\\pi × 2.5 × 10^{-7}}{1} ≈ 7.85398 × 10^{-7} \) m².\n\nThus, the resistance with doubled diameter,\n\n\( R' = \\rho \\frac{l}{A'} =1.6×10^{-8} × \\frac{122.72}{7.85398 × 10^{-7}} ≈ 2.5 \) Ω.\n\nTherefore, the resistance decreases to 2.5 Ω when the diameter is doubled.",
    "topic": "Electrical Resistivity and Resistance Calculation",
    "bloom_level": "Apply"
  },
  {
    "question_text": "The values of current \( I \) flowing in a given resistor for the corresponding values of potential difference \( V \) across the resistor are given below:\n\n\[\n\\begin{array}{c|ccccc}\nI \\, (\\text{amperes}) & 0.5 & 1.0 & 2.0 & 3.0 & 4.0 \\\\\n\\hline\nV \\, (\\text{volts}) & 1.6 & 3.4 & 6.7 & 10.2 & 13.2 \\\\\n\\end{array}\n\]\n\nPlot a graph between \( V \) and \( I \) and calculate the resistance of that resistor.",
    "type": "Numerical",
    "difficulty": "Medium",
    "options": null,
    "correct_answer": "The resistance of the resistor is approximately 3.4 Ω.",
    "explanation": "To determine the resistance \( R \\), we can use Ohm’s law, \( R = \\frac{V}{I} \\), for each pair of \( V \) and \( I \\):\n\n\[\n\\begin{align*}\nR_1 &= \\frac{1.6}{0.5} = 3.2 \, \\Omega \\\\\nR_2 &= \\frac{3.4}{1.0} = 3.4 \, \\Omega \\\\\nR_3 &= \\frac{6.7}{2.0} = 3.35 \, \\Omega \\\\\nR_4 &= \\frac{10.2}{3.0} = 3.4 \, \\Omega \\\\\nR_5 &= \\frac{13.2}{4.0} = 3.3 \, \\Omega \\\\\n\\end{align*}\n\]\n\nThe resistance values are consistent and approximately equal to 3.4 Ω. Therefore, the resistance of the resistor is 3.4 Ω.\n\nWhen plotting \( V \) against \( I \\), the graph will be a straight line passing through the origin with a slope equal to the resistance \( R \\). The slope calculated from the graph will also give \( R ≈ 3.4 \, \\Omega \\).",
    "topic": "Ohm’s Law and Resistance Calculation",
    "bloom_level": "Apply"
  },
  {
    "question_text": "When a 12 V battery is connected across an unknown resistor, there is a current of 2.5 mA in the circuit. Find the value of the resistance of the resistor.",
    "type": "Numerical",
    "difficulty": "Easy",
    "options": null,
    "correct_answer": "The resistance of the resistor is 4,800 Ω (4.8 kΩ).",
    "explanation": "Using Ohm’s law, \( R = \\frac{V}{I} \\), where \( V = 12 \, \\text{V} \\) and \( I = 2.5 \, \\text{mA} = 0.0025 \, \\text{A} \\). Thus,\n\n\[ R = \\frac{12}{0.0025} = 4,800 \, \\Omega \\). Therefore, the resistance is 4,800 Ω or 4.8 kΩ.",
    "topic": "Ohm’s Law - Resistance Calculation",
    "bloom_level": "Apply"
  },
  {
    "question_text": "A battery of 9 V is connected in series with resistors of 0.2 Ω, 0.3 Ω, 0.4 Ω, 0.5 Ω, and 12 Ω, respectively. How much current would flow through the 12 Ω resistor?",
    "type": "Numerical",
    "difficulty": "Easy",
    "options": null,
    "correct_answer": "Approximately 0.67 A of current would flow through the 12 Ω resistor.",
    "explanation": "Since the resistors are connected in series, the same current flows through each resistor. First, calculate the total resistance \( R_{total} \\):\n\n\[ R_{total} = 0.2 + 0.3 + 0.4 + 0.5 + 12 = 13.4 \, \\Omega \\).\n\nUsing Ohm’s law,\n\n\[ I = \\frac{V}{R_{total}} = \\frac{9}{13.4} ≈ 0.6716 \, \\text{A} \\).\n\nTherefore, approximately 0.67 A of current flows through the 12 Ω resistor.",
    "topic": "Series Resistors and Current Calculation",
    "bloom_level": "Apply"
  },
  {
    "question_text": "How many 176 Ω resistors (in parallel) are required to carry 5 A on a 220 V line?",
    "type": "Numerical",
    "difficulty": "Medium",
    "options": null,
    "correct_answer": "4 resistors are required.",
    "explanation": "First, calculate the total resistance needed for the circuit using Ohm’s law:\n\n\[ R_{total} = \\frac{V}{I} = \\frac{220 \\, \\text{V}}{5 \\, \\text{A}} = 44 \\, \\Omega \\).\n\nFor N resistors of 176 Ω connected in parallel, the equivalent resistance \( R_{eq} \\) is:\n\n\[ \\frac{1}{R_{eq}} = N \\times \\frac{1}{176} \\).\n\nSince \( R_{eq} = R_{total} = 44 \\, \\Omega \\),\n\n\[ \\frac{1}{44} = \\frac{N}{176} \\Rightarrow N = \\frac{176}{44} = 4 \\).\n\nTherefore, 4 resistors of 176 Ω each are required in parallel to achieve a total resistance of 44 Ω, allowing a current of 5 A to flow from a 220 V source.",
    "topic": "Parallel Resistors and Current Calculation",
    "bloom_level": "Apply"
  },
  {
    "question_text": "Show how you would connect three resistors, each of resistance 6 Ω, so that the combination has a resistance of (i) 9 Ω, (ii) 4 Ω.",
    "type": "Short Answer",
    "difficulty": "Medium",
    "options": null,
    "correct_answer": "(i) Connect two resistors in parallel and then connect the third resistor in series with this parallel combination to get 9 Ω.\n\n(ii) Connect one resistor in parallel with the series combination of the other two resistors to get 4 Ω.",
    "explanation": "(i) To achieve a total resistance of 9 Ω:\n- Connect two 6 Ω resistors in parallel:\n  \n  \[ R_p = \\frac{6 × 6}{6 + 6} = \\frac{36}{12} = 3 \\, \\Omega \\).\n\n- Connect the third 6 Ω resistor in series with the parallel combination:\n  \n  \[ R_{total} = R_p + R = 3 + 6 = 9 \\, \\Omega \\).\n\n(ii) To achieve a total resistance of 4 Ω:\n- Connect two 6 Ω resistors in series to get 12 Ω.\n- Then, connect the third 6 Ω resistor in parallel with this 12 Ω combination:\n  \n  \[ R_{eq} = \\frac{6 × 12}{6 + 12} = \\frac{72}{18} = 4 \\, \\Omega \\).\n\nTherefore, the required connections are as described to obtain total resistances of 9 Ω and 4 Ω respectively.",
    "topic": "Combination of Resistors",
    "bloom_level": "Apply"
  },
  {
    "question_text": "Several electric bulbs designed to be used on a 220 V electric supply line, are rated 10 W. How many lamps can be connected in parallel with each other across the two wires of a 220 V line if the maximum allowable current is 5 A?",
    "type": "Numerical",
    "difficulty": "Medium",
    "options": null,
    "correct_answer": "110 lamps can be connected.",
    "explanation": "First, determine the current drawn by one bulb:\n\nUsing power formula, \( P = VI \\Rightarrow I = \\frac{P}{V} = \\frac{10 \\, \\text{W}}{220 \\, \\text{V}} ≈ 0.04545 \\, \\text{A} \\) per bulb.\n\nTo find the number of bulbs that can be connected without exceeding the maximum allowable current of 5 A:\n\n\[ N = \\frac{I_{total}}{I_{per \\, bulb}} = \\frac{5}{0.04545} ≈ 110 \\).\n\nTherefore, up to 110 bulbs can be connected in parallel across a 220 V supply without exceeding a total current of 5 A.",
    "topic": "Parallel Circuits and Current Calculation",
    "bloom_level": "Apply"
  },
  {
    "question_text": "A hot plate of an electric oven connected to a 220 V line has two resistance coils A and B, each of 24 Ω resistance, which may be used separately, in series, or in parallel. What are the currents in the three cases?",
    "type": "Short Answer",
    "difficulty": "Medium",
    "options": null,
    "correct_answer": "When used separately: approximately 9.17 A.\nWhen connected in series: approximately 4.58 A.\nWhen connected in parallel: approximately 18.33 A.",
    "explanation": "1. **Used Separately**:\n   - Each coil has resistance \( R = 24 \, \\Omega \\).\n   - Current \( I = \\frac{V}{R} = \\frac{220}{24} ≈ 9.17 \, \\text{A} \\).\n\n2. **Connected in Series**:\n   - Total resistance \( R_{series} = 24 + 24 = 48 \, \\Omega \\).\n   - Current \( I = \\frac{220}{48} ≈ 4.58 \, \\text{A} \\).\n\n3. **Connected in Parallel**:\n   - Total resistance \( R_{parallel} = \\frac{24}{2} = 12 \, \\Omega \\).\n   - Current \( I = \\frac{220}{12} ≈ 18.33 \, \\text{A} \\).\n\nTherefore, the currents in the three cases are approximately 9.17 A, 4.58 A, and 18.33 A respectively.",
    "topic": "Combination of Resistors - Currents",
    "bloom_level": "Apply"
  },
  {
    "question_text": "Compare the power used in the 2 Ω resistor in each of the following circuits:\n\n- (i) a 6 V battery in series with 1 Ω and 2 Ω resistors, and \n\n- (ii) a 4 V battery in parallel with 12 Ω and 2 Ω resistors.",
    "type": "Short Answer",
    "difficulty": "Hard",
    "options": null,
    "correct_answer": "The power used in the 2 Ω resistor is 8 W in both cases.",
    "explanation": "\n**Case (i): Series Circuit**\n- Total resistance \( R_{total} = 1 + 2 = 3 \, \\Omega \\).\n- Current \( I = \\frac{V}{R} = \\frac{6}{3} = 2 \, \\text{A} \\).\n- Voltage across 2 Ω resistor \( V_{2} = I \\times R = 2 \\times 2 = 4 \, \\text{V} \\).\n- Power \( P = \\frac{V_{2}^2}{R} = \\frac{4^2}{2} = 8 \, \\text{W} \\).\n\n**Case (ii): Parallel Circuit**\n- Two resistors (12 Ω and 2 Ω) connected in parallel across 4 V.\n- Current through 2 Ω resistor \( I = \\frac{V}{R} = \\frac{4}{2} = 2 \, \\text{A} \\).\n- Power \( P = I^2 R = 2^2 \\times 2 = 8 \, \\text{W} \\).\n\n**Comparison**:\n- In both circuits, the 2 Ω resistor dissipates the same power of 8 W.",
    "topic": "Power in Resistors in Series and Parallel",
    "bloom_level": "Analyze"
  },
  {
    "question_text": "Two lamps, one rated 100 W at 220 V, and the other 60 W at 220 V, are connected in parallel to the electric mains supply. What current is drawn from the line if the supply voltage is 220 V?",
    "type": "Numerical",
    "difficulty": "Easy",
    "options": null,
    "correct_answer": "Approximately 0.73 A of current is drawn from the line.",
    "explanation": "For each lamp, calculate the current using \( I = \\frac{P}{V} \\):\n\n- **100 W lamp**:\n  \n  \( I_1 = \\frac{100}{220} ≈ 0.4545 \, \\text{A} \\).\n\n- **60 W lamp**:\n  \n  \( I_2 = \\frac{60}{220} ≈ 0.2727 \, \\text{A} \\).\n\nSince the lamps are connected in parallel, the total current drawn from the mains is the sum of the individual currents:\n\n\[ I_{total} = I_1 + I_2 ≈ 0.4545 + 0.2727 ≈ 0.7272 \, \\text{A} \\).\n\nTherefore, approximately 0.73 A of current is drawn from the line.",
    "topic": "Parallel Circuits - Current Calculation",
    "bloom_level": "Apply"
  },
  {
    "question_text": "Which uses more energy, a 250 W TV set in 1 hr, or a 1200 W toaster in 10 minutes?",
    "type": "Short Answer",
    "difficulty": "Easy",
    "options": null,
    "correct_answer": "The 250 W TV set uses more energy.",
    "explanation": "Calculate energy consumed by both devices using \( Energy = Power \\times Time \\).\n\n- **TV**:\n  \n  \( Energy = 250 \, \\text{W} \\times 1 \, \\text{hr} = 250 \, \\text{Wh} \\).\n\n- **Toaster**:\n  \n  \( Time = 10 \, \\text{minutes} = \\frac{10}{60} \, \\text{hr} = \\frac{1}{6} \, \\text{hr} \\).\n  \n  \( Energy = 1200 \, \\text{W} \\times \\frac{1}{6} \, \\text{hr} = 200 \, \\text{Wh} \\).\n\nThus, the TV consumes 250 Wh while the toaster consumes 200 Wh. Therefore, the TV uses more energy.",
    "topic": "Energy Consumption",
    "bloom_level": "Apply"
  },
  {
    "question_text": "An electric heater of resistance 44 Ω draws 5 A from the service mains for 2 hours. Calculate the rate at which heat is developed in the heater.",
    "type": "Numerical",
    "difficulty": "Medium",
    "options": null,
    "correct_answer": "The rate at which heat is developed in the heater is 1,100 W.",
    "explanation": "The rate at which heat is developed in an electric heater is equal to the electrical power consumed, which can be calculated using Ohm’s law:\n\n\[ P = I^2 R \\).\n\nGiven:\n\n- \( I = 5 \, \\text{A} \\)\n- \( R = 44 \, \\Omega \\)\n\nThus,\n\n\[ P = 5^2 × 44 = 25 × 44 = 1,100 \, \\text{W} \\).\n\nTherefore, the heater develops heat at a rate of 1,100 W.",
    "topic": "Power Calculation in Resistors",
    "bloom_level": "Apply"
  },
  {
    "question_text": "Explain the following:\n\n(a) Why is tungsten used almost exclusively for the filament of electric lamps?\n\n(b) Why are the conductors of electric heating devices, such as bread-toasters and electric irons, made of an alloy rather than a pure metal?\n\n(c) Why is the series arrangement not used for domestic circuits?\n\n(d) How does the resistance of a wire vary with its area of cross-section?\n\n(e) Why are copper and aluminium wires usually employed for electricity transmission?",
    "type": "Long Answer",
    "difficulty": "Hard",
    "options": null,
    "correct_answer": " \n(a) **Tungsten is used almost exclusively for the filament of electric lamps because of its high melting point and low vapor pressure.** Tungsten can withstand high temperatures without melting, allowing the filament to glow brightly without evaporating rapidly, which ensures the longevity of the lamp.\n\n(b) **Conductors of electric heating devices are made of alloys rather than pure metals to achieve higher resistivity and better durability at high temperatures.** Alloys like nichrome have higher resistivity than pure metals, which allows them to generate more heat for a given current. Additionally, alloys are more resistant to oxidation and degradation at high temperatures compared to pure metals, enhancing the lifespan of heating elements.\n\n(c) **Series arrangement is not used for domestic circuits because failure in any one device would interrupt the entire circuit, cutting off power to all devices.** In domestic settings, appliances are preferred to operate independently; a parallel arrangement ensures that if one appliance fails, others continue to function.\n\n(d) **The resistance of a wire is inversely proportional to its area of cross-section.** As the area of cross-section increases, more pathways are available for the flow of electrons, reducing resistance. Mathematically, \( R \\propto \\frac{1}{A} \\).\n\n(e) **Copper and aluminium wires are usually employed for electricity transmission because they have low resistivity, which minimizes energy loss as heat, and good ductility, which makes them easy to draw into wires.** Copper has excellent electrical conductivity, while aluminium is lightweight and cost-effective, making it suitable for efficient and practical electricity transmission over long distances.",
    "explanation": "Each subpart requires an explanation based on the properties of materials and circuit configurations:\n\n(a) **Tungsten Filaments**: Tungsten’s exceptionally high melting point (~3422°C) and low vapor pressure make it ideal for lamp filaments that need to emit light at high temperatures without evaporating quickly, ensuring longer lamp life.\n\n(b) **Alloy Conductors in Heating Devices**: Alloys like nichrome combine metals to enhance resistivity and thermal stability. Pure metals may oxidize or degrade under prolonged high temperatures, while alloys resist such deterioration and provide consistent heating.\n\n(c) **Series Circuits in Domestic Use**: In a series circuit, if one device fails or is turned off, the entire circuit is broken, stopping current flow. For convenience and reliability, domestic circuits use parallel arrangements so that each appliance operates independently.\n\n(d) **Resistance and Cross-sectional Area**: Resistance \( R \\) is given by \( R = \\rho \\frac{l}{A} \\), where \( A \\) is the cross-sectional area. Increasing \( A \\) decreases \( R \\), facilitating easier current flow.\n\n(e) **Copper and Aluminium for Transmission**: Copper offers the highest electrical conductivity and is highly malleable, making it easy to install. Aluminium, while slightly less conductive, is lighter and cheaper, making it suitable for long-distance transmission where weight and cost are critical factors.",
    "topic": "Material Properties and Circuit Configurations",
    "bloom_level": "Understand"
  }
]
```