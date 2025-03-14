gunicorn --bind=0.0.0.0:$PORT --timeout 600 app:app
Name: WEBSITES_PORT
   Value: 8000

   Name: SCM_DO_BUILD_DURING_DEPLOYMENT
   Value: true

   Name: WEBSITE_WEBDEPLOY_USE_SCM
   Value: true