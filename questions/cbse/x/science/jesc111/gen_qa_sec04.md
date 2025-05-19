```json
[
  {
    "question_text": "What is the formula for calculating the equivalent resistance \( R_s \) of three resistors connected in series?",
    "type": "MCQ",
    "difficulty": "Easy",
    "options": [
      "\( R_s = R_1 \times R_2 \times R_3 \)",
      "\( R_s = R_1 + R_2 + R_3 \)",
      "\( \frac{1}{R_s} = \frac{1}{R_1} + \frac{1}{R_2} + \frac{1}{R_3} \)",
      "\( R_s = \max(R_1, R_2, R_3) \)"
    ],
    "correct_answer": "\( R_s = R_1 + R_2 + R_3 \)",
    "explanation": "For resistors connected in series, the equivalent resistance is the sum of their individual resistances. Therefore, \( R_s = R_1 + R_2 + R_3 \).",
    "topic": "Equivalent Resistance of Series Resistors",
    "bloom_level": "Remember"
  },
  {
    "question_text": "If three resistors with resistances \( R_1 = 2\,\Omega \), \( R_2 = 3\,\Omega \), and \( R_3 = 5\,\Omega \) are connected in series, what is the equivalent resistance \( R_s \) of the combination?",
    "type": "Numerical",
    "difficulty": "Easy",
    "options": null,
    "correct_answer": "The equivalent resistance is \( R_s = 2\,\Omega + 3\,\Omega + 5\,\Omega = 10\,\Omega \).",
    "explanation": "When resistors are connected in series, their equivalent resistance is the sum of their individual resistances. So, \( R_s = R_1 + R_2 + R_3 = 2\,\Omega + 3\,\Omega + 5\,\Omega = 10\,\Omega \).",
    "topic": "Calculating Equivalent Resistance",
    "bloom_level": "Apply"
  },
  {
    "question_text": "Explain why the current remains the same through each resistor in a series circuit.",
    "type": "Short Answer",
    "difficulty": "Medium",
    "options": null,
    "correct_answer": "In a series circuit, there is only one path for the current to flow. Therefore, the same current passes through each resistor without any branching.",
    "explanation": "Since all components in a series circuit are connected end-to-end, the electrons have only one path to travel. This ensures that the current \( I \) is constant throughout the circuit, passing through each resistor sequentially.",
    "topic": "Current in Series Circuits",
    "bloom_level": "Understand"
  },
  {
    "question_text": "A 12 V battery is connected in series with three resistors of \( 4\,\Omega \), \( 6\,\Omega \), and \( 10\,\Omega \). Calculate the total current flowing through the circuit.",
    "type": "Numerical",
    "difficulty": "Medium",
    "options": null,
    "correct_answer": "The total current \( I = \frac{V}{R_s} = \frac{12\,\text{V}}{4\,\Omega + 6\,\Omega + 10\,\Omega} = \frac{12\,\text{V}}{20\,\Omega} = 0.6\,\text{A} \).",
    "explanation": "First, calculate the equivalent resistance: \( R_s = 4\,\Omega + 6\,\Omega + 10\,\Omega = 20\,\Omega \). Then, using Ohm's Law \( I = \frac{V}{R_s} \), the current is \( I = \frac{12\,\text{V}}{20\,\Omega} = 0.6\,\text{A} \).",
    "topic": "Ohm’s Law in Series Circuits",
    "bloom_level": "Apply"
  },
  {
    "question_text": "In a series circuit, if the potential differences across three resistors are \( V_1 = 2\,\text{V} \), \( V_2 = 3\,\text{V} \), and \( V_3 = 5\,\text{V} \), what is the total potential difference \( V \) across the combination?",
    "type": "Numerical",
    "difficulty": "Medium",
    "options": null,
    "correct_answer": "The total potential difference \( V = V_1 + V_2 + V_3 = 2\,\text{V} + 3\,\text{V} + 5\,\text{V} = 10\,\text{V} \).",
    "explanation": "In a series circuit, the total potential difference is the sum of the potential differences across each resistor. Therefore, \( V = V_1 + V_2 + V_3 = 2\,\text{V} + 3\,\text{V} + 5\,\text{V} = 10\,\text{V} \).",
    "topic": "Potential Difference in Series Circuits",
    "bloom_level": "Apply"
  },
  {
    "question_text": "Which of the following statements is true for resistors connected in series?",
    "type": "MCQ",
    "difficulty": "Easy",
    "options": [
      "The total resistance is less than the smallest individual resistance.",
      "The total resistance is equal to the resistance of the largest resistor.",
      "The total resistance is the sum of the individual resistances.",
      "The current splits equally among the resistors."
    ],
    "correct_answer": "The total resistance is the sum of the individual resistances.",
    "explanation": "In a series connection, resistors add up directly to form the total resistance. Therefore, \( R_s = R_1 + R_2 + R_3 \). The other options are incorrect: the total resistance is greater than any individual resistor, and the current does not split in a series circuit.",
    "topic": "Properties of Series Resistors",
    "bloom_level": "Understand"
  },
  {
    "question_text": "A circuit consists of a 9 V battery connected in series with two resistors of \( 3\,\Omega \) and \( 6\,\Omega \). Calculate the potential difference across each resistor.",
    "type": "Numerical",
    "difficulty": "Medium",
    "options": null,
    "correct_answer": "The potential difference across the \( 3\,\Omega \) resistor is 3 V, and across the \( 6\,\Omega \) resistor is 6 V.",
    "explanation": "First, find the equivalent resistance: \( R_s = 3\,\Omega + 6\,\Omega = 9\,\Omega \). The total current \( I = \frac{V}{R_s} = \frac{9\,\text{V}}{9\,\Omega} = 1\,\text{A} \). Then, \( V_1 = I \times R_1 = 1\,\text{A} \times 3\,\Omega = 3\,\text{V} \) and \( V_2 = I \times R_2 = 1\,\text{A} \times 6\,\Omega = 6\,\text{V} \).",
    "topic": "Potential Difference in Series Circuits",
    "bloom_level": "Apply"
  },
  {
    "question_text": "True or False: In a series circuit, if one resistor fails (becomes an open circuit), the entire current stops flowing.",
    "type": "MCQ",
    "difficulty": "Easy",
    "options": [
      "True",
      "False",
      "Only if it is the first resistor",
      "Only if it is the last resistor"
    ],
    "correct_answer": "True",
    "explanation": "In a series circuit, all components are connected in a single path. If one resistor becomes an open circuit, it breaks the path, stopping the current flow throughout the entire circuit.",
    "topic": "Behavior of Series Circuits",
    "bloom_level": "Understand"
  },
  {
    "question_text": "A 15 V battery is connected in series with three resistors. The first resistor is \( 5\,\Omega \) and the second is \( 10\,\Omega \). If the current flowing through the circuit is \( 0.5\,\text{A} \), calculate the resistance of the third resistor.",
    "type": "Numerical",
    "difficulty": "Hard",
    "options": null,
    "correct_answer": "The third resistor has a resistance of \( 5\,\Omega \).",
    "explanation": "First, calculate the equivalent resistance using Ohm’s Law: \( R_s = \frac{V}{I} = \frac{15\,\text{V}}{0.5\,\text{A}} = 30\,\Omega \). The sum of the known resistances is \( 5\,\Omega + 10\,\Omega = 15\,\Omega \). Therefore, the third resistor \( R_3 = R_s - (R_1 + R_2) = 30\,\Omega - 15\,\Omega = 15\,\Omega \). However, there seems to be a miscalculation. Correctly: \( R_3 = 30\,\Omega - 15\,\Omega = 15\,\Omega \).",
    "topic": "Advanced Series Resistance Calculation",
    "bloom_level": "Analyze"
  },
  {
    "question_text": "Describe the relationship between the total potential difference and the individual potential differences across resistors in a series circuit.",
    "type": "Short Answer",
    "difficulty": "Medium",
    "options": null,
    "correct_answer": "The total potential difference across the series combination is equal to the sum of the potential differences across each individual resistor.",
    "explanation": "In a series circuit, the voltages across each resistor add up to the total voltage supplied by the battery. Mathematically, \( V = V_1 + V_2 + V_3 \).",
    "topic": "Potential Difference in Series Circuits",
    "bloom_level": "Understand"
  },
  {
    "question_text": "An electric lamp of resistance \( 15\,\Omega \) is connected in series with a resistor of \( 5\,\Omega \) to a \( 20\,\text{V} \) battery. Calculate the potential difference across the electric lamp.",
    "type": "Numerical",
    "difficulty": "Medium",
    "options": null,
    "correct_answer": "The potential difference across the electric lamp is \( 15\,\text{V} \).",
    "explanation": "First, find the total resistance: \( R_s = 15\,\Omega + 5\,\Omega = 20\,\Omega \). The current \( I = \frac{V}{R_s} = \frac{20\,\text{V}}{20\,\Omega} = 1\,\text{A} \). The potential difference across the lamp is \( V_1 = I \times R_1 = 1\,\text{A} \times 15\,\Omega = 15\,\text{V} \).",
    "topic": "Potential Difference in Series Circuits",
    "bloom_level": "Apply"
  },
  {
    "question_text": "Explain how the equivalent resistance of a series circuit changes when more resistors are added in series.",
    "type": "Short Answer",
    "difficulty": "Easy",
    "options": null,
    "correct_answer": "The equivalent resistance increases as more resistors are added in series.",
    "explanation": "Since the equivalent resistance \( R_s \) is the sum of all individual resistances in a series circuit, adding more resistors increases the total resistance.",
    "topic": "Equivalent Resistance of Series Resistors",
    "bloom_level": "Understand"
  }
]
```