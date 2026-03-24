Starting html and css files
html_info/template.css
html_info/template.html

Algorithm:

# Step : 1  Using html_pipeline/render_html.py, render following file 
- html_pipeline/resume.css
- html_pipeline/resume.html
- image_reference/Output_1.png

Uses 
- html_info/template.css
- html_info/template.html


# Step : 2 Run ./pipeline.sh full to generate 
- output/Output_1/objects.csv
- output/Page_1/objects.csv


# Step : 3 Use optimization/pipeline.py to

optimize the location of objects in 
- html_info/template.css
- html_info/template.html

based on
- output/Output_1/objects.csv
- output/Page_1/objects.csv


optimize the color of the objects in
- html_info/template.css
- html_info/template.html

based on 
- image_reference/Output_1.png
- image_reference/Page_1.png
- output/Output_1/objects.csv
- output/Page_1/objects.csv

# Step : 4 Repeat steps
Repeat Steps 1-3 till the expected performance is achieved