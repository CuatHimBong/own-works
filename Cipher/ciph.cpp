#include <iostream>
#include <string>

int main() {
  char alphabet[26] = {'A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M', 'N', 'O', 'P', 'Q', 'R', 'S', 'T', 'U', 'V', 'W', 'X', 'Y', 'Z'};
  std::string word = "";

  std::cin >> word;

  unsigned int size = word.size();
  char* wordp = new char[size];

  word.copy(wordp, size, 0);

  for (int i = 0; i < size; i++) {
    std::cout << wordp[i];
  }
  std::cout << "\n";

  delete[] wordp;
}

