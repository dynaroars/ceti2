int mainQ(int in,int up, int down) {
     int bias, r;
     if (in!=0)
	  bias = down;
     else
	  bias = up;
     if (bias > down)
	  r = 1;
     else
	  r = 0;
     return r;
}

int main(int argc, char* argv[]){
     int rv = mainQ(atoi(argv[1]), atoi(argv[2]), atoi(argv[3]));
     return 0;
}

