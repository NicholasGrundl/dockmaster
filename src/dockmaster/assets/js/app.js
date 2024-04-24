
class App {
   constructor() {
   }
   init() {
      
      this.user = null
      this.refreshLoginState()

      //Events
      $('#auth-login-button').click(() => {
         if (this.user!=null) {
            UIkit.notification("already logged in", {status: 'primary', timeout:300})
         } else {
            window.location.replace('/auth/login')
         }
      });

      $('#auth-logout-button').click(() => {
         if (this.user!=null) {
            window.location.assign('/auth/logout')
         } else {
            UIkit.notification("already logged out", {status: 'primary', timeout:300})
         }
      });

   }
   
   refreshLoginState(onresult) {
      /**
       * Calls the server endpoint to get the principal profile
       * - if authenticated returns the principal profile
       * - if not authenticated returns an empty object
       * - refreshes the state of the view
       */
      let authenticationStateUrl = './auth/principal';
  
      fetch(authenticationStateUrl)
      .then(response => {
         if (!response.ok) {
            throw new Error('Network response was not ok');
         }
         return response.json();
      })
      .then(data => {
         if (Object.keys(data).length === 0) {
            console.log('setting logged out state')
            this.setLoggedOutState();
         } else {
            console.log('setting logged in state')
            this.setLoggedInState(data);
         }
         //run the wrapped function
         if (onresult) {
            onresult()
         }
      })
      .catch(error => {
         this.catchLoginError(error)
      });
   }

   setLoggedInState(data) {
      /**
       * When logged in we
       * - set the user property to the profile data
       * - hide the login view and show the logout view
       */
      console.log('user profile data:',data)
      this.user = data
      //Show login or logout elements
      $("#auth-login-view").addClass('uk-invisible') 
      $("#auth-logout-view").removeClass('uk-invisible') 
      //Update login data
      $("#auth-state-badge").text('Authenticated').addClass('uk-badge-success').removeClass('uk-badge-warning')
      $("#auth-user-name").text(this.user.name)
      $("#auth-user-email").text(this.user.email)
      $("#auth-user-photo").attr('src', this.user.picture)
   }

   setLoggedOutState() {
      /**
       * When logged out we
       * - set the user property to null
       * - hide the logout view and show the login view
       */
      this.user = null
      //Show login or logout elements
      $("#auth-login-view").removeClass('uk-invisible') 
      $("#auth-logout-view").addClass('uk-invisible') 
      //Update login data
      $("#auth-state-badge").text('Not Authenticated').addClass('uk-badge-warning').removeClass('uk-badge-success')
      $("#auth-user-name").text('')
      $("#auth-user-email").text('')
      $("#auth-user-photo").attr('src', '')
   }

   catchLoginError(error) {
      UIkit.notification("error with login", {status: 'warning'})
      console.error('Error:', error)
      this.setLoggedOutState()
   }
  
}

app = new App()

UIkit.util.ready(function() { app.init(); })
