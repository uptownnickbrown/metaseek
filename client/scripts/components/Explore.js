import React from 'react';
import axios from 'axios';
import apiConfig from '../config/api.js';
import Firebase from 'firebase';

import MuiThemeProvider from 'material-ui/styles/MuiThemeProvider';
import getMuiTheme from 'material-ui/styles/getMuiTheme';
import ColorPalette from './ColorPalette';

import Paper from 'material-ui/Paper';
import RaisedButton from 'material-ui/RaisedButton';
import FlatButton from 'material-ui/FlatButton';
import Dialog from 'material-ui/Dialog';
import TextField from 'material-ui/TextField';
import SelectField from 'material-ui/SelectField';
import MenuItem from 'material-ui/MenuItem';
import IconButton from 'material-ui/IconButton';

// My component imports
import Header from './Header';
import ExploreFilters from './ExploreFilters';
import Loading from './Loading';
import VizDashboard from './VizDashboard';
import ExploreTable from './ExploreTable';

import {getReadableFileSizeString} from '../helpers';
import ContentForward from 'material-ui/svg-icons/content/forward';

var apiRequest = axios.create({
  baseURL: apiConfig.baseURL
});

var Explore = React.createClass({
  getInitialState : function() {
    return {
      'fullSummaryData':[],
      'activeSummaryData': [],
      'filter_params':JSON.stringify({'rules':[]}),
      'loaded':false,
      'processing':false,
      'firebase':{
        'uid':null,
        'name':null,
        'photo':null
      },
      'filtersOpen': true,
      'submitDiscoveryOpen': false,
      'discoveryTitle': '',
      'discoveryDescription':'',
      'promptLoginOpen': false
    }
  },

  componentWillMount : function() {
    var user = Firebase.auth().currentUser;
    if (user) {
      this.state.firebase.name = user.displayName;
      this.state.firebase.uid = user.uid;
      this.state.firebase.photo = user.photoURL;
      this.setState({"firebase": this.state.firebase});
    }
    var self = this;
    apiRequest.get("/datasets/summary")
    .then(function (response) {
      self.setState({"fullSummaryData": response.data.summary,"activeSummaryData": response.data.summary});
      apiRequest.post("/datasets/search/1", {
        "filter_params":self.state.filter_params,
      }).then(function (response) {
        self.setState({"dataTable":response.data,"loaded":true});
      })
    });
  },

  updateActiveSummaryData : function() {
    var self = this;
    self.setState({"processing":true});
    apiRequest.post("/datasets/search/summary", {
      "filter_params":self.state.filter_params
    }).then(function (response) {
      self.setState({"activeSummaryData": response.data.summary});
      apiRequest.post("/datasets/search/1", {
        "filter_params":self.state.filter_params
      }).then(function (response) {
        self.setState({"dataTable":response.data,"processing":false});
      });
    });
  },

  getPreviousDataPage : function() {
    var self = this;
    apiRequest.post(self.state.dataTable.previousUri, {
      "filter_params":self.state.filter_params
    }).then(function (response) {
      self.setState({"dataTable":response.data});
    });
  },

  getNextDataPage : function() {
    var self = this;
    apiRequest.post(self.state.dataTable.nextUri, {
      "filter_params":self.state.filter_params
    }).then(function (response) {
      self.setState({"dataTable":response.data});
    });
  },

  triggerGoogleLogin : function() {
    this.setState({"promptLoginOpen":false});
    var successfulLogin = this.successfulLogin;
    var provider = new Firebase.auth.GoogleAuthProvider();
    var auth = Firebase.auth().signInWithPopup(provider).then(function(result) {
      var user = result.user;
      successfulLogin(user);
    }).catch(function(error) {
      console.log("couldn't log in for some reason");
      console.log(error);
    });
  },

  triggerLogout : function() {
    var accountComponent = this;
    var auth = Firebase.auth().signOut().then(function() {
      accountComponent.state.firebase.name = null;
      accountComponent.state.firebase.uid = null;
      accountComponent.state.firebase.photo = null;
      accountComponent.setState(accountComponent.state.firebase);
    }, function(error) {
      console.log("couldn't log out for some reason");
      console.log(error);
    });
  },


  successfulLogin : function(user) {
    var self = this;
    self.state.firebase.name = user.displayName;
    self.state.firebase.uid = user.uid;
    self.state.firebase.photo = user.photoURL;
    apiRequest.post("/user/create", {
      "firebase_id":self.state.firebase.uid,
      "admin":0
    }).then(function(response){
      self.setState({"firebase": self.state.firebase});
    });
  },

  promptGoogleLoginOpen: function() {
    this.setState({'promptLoginOpen':true});
  },

  promptGoggleLoginClose : function() {
    this.setState({'promptLoginOpen':false})
  },

  discoveryDialogOpen : function() {
    this.setState({'submitDiscoveryOpen': true});
  },

  discoveryDialogClose : function () {
    this.setState({'submitDiscoveryOpen': false, 'discoveryTitle': null});
  },

  updateDiscoveryTitle : function(event, newValue) {
    this.setState({'discoveryTitle':newValue});
  },

  updateDiscoveryDescription : function(event, newValue) {
    this.setState({'discoveryDescription':newValue});
  },

  submitDiscovery : function() {
    var self = this;
    apiRequest.post("/discovery/create", {
      "owner_id":self.state.firebase.uid,
      "filter_params":self.state.filter_params,
      "discovery_title":self.state.discoveryTitle,
      "discovery_description":self.state.discoveryDescription
    }).then(function (response) {
      self.props.history.push("/discovery/" + response.data.discovery.id);
    });
    this.setState({'submitDiscoveryOpen': false});
  },

  updateFilterParams : function(filterStates) {
    filterStates = Object.values(filterStates).filter(function(ruleObject){
      if (ruleObject.value == "All" || ruleObject.value=="" || ruleObject.value=="[]") {
        return false;
      }
      if (("field" in ruleObject) && ("value" in ruleObject) && ("type" in ruleObject)) {
        return true;
      } else {
        return false;
      }
    });
    this.state.filter_params = JSON.stringify({"rules":filterStates});
    this.setState({"filter_params":JSON.stringify({"rules":filterStates})});
    this.updateActiveSummaryData();
  },

  toggleFilters : function() {
    this.setState({filtersOpen: !this.state.filtersOpen});

  },

  render : function() {
    if (!this.state.loaded) return <Loading/>;

    const discoveryDialog_actions = [
      <FlatButton
        label="Cancel"
        primary={true}
        onClick={this.discoveryDialogClose}
      />,
    <RaisedButton
        label="Submit Discovery"
        primary={true}
        onClick={this.submitDiscovery}
        disabled={this.state.discoveryTitle ? false : true}
      />
    ];

    const loginPrompt_actions = [
      <RaisedButton
        label="Log in with Google"
        primary={true}
        onClick={this.triggerGoogleLogin}
      />
    ];

    return (
      <div>

          <MuiThemeProvider muiTheme={getMuiTheme(ColorPalette)}>
            <div>
              <IconButton  style={{position:"fixed", top: "100px", left:"-35px"}} iconStyle={{color:"rgb(175,175,175)", width: "100px", height:"60px"}} onClick={this.toggleFilters}>
                  <ContentForward />
              </IconButton>
              <text style={{position:"fixed",top:"170px", left:"5px", color:"rgb(175,175,175)", fontFamily:"Roboto"}}>Edit Filters</text>
              <div className={this.state.filtersOpen ? "header-explore-filteropen" : "header-explore"}>
                <Header history={this.props.history}/>
              </div>
              <div className={this.state.filtersOpen ? "explore-container-filteropen" : "explore-container"}>
                <h2>Explore</h2>
                <div className="save-discovery-button-container">
                  <RaisedButton
                    className="save-discovery-button"
                    onClick={this.state.firebase.uid ? this.discoveryDialogOpen : this.promptGoogleLoginOpen}
                    primary={true}
                    label="Save Discovery"
                  />
                  <Dialog
                    title="Title Your Discovery"
                    actions={discoveryDialog_actions}
                    modal={false}
                    open={this.state.submitDiscoveryOpen}
                    onRequestClose={this.discoveryDialogClose}
                  >
                    <TextField
                      errorText="This field is required."
                      errorStyle={{color:"#FEB28D"}}
                      underlineFocusStyle={{color:"#979CF2"}}
                      onChange={this.updateDiscoveryTitle}
                      value={this.state.discoveryTitle}
                      fullWidth={true}
                    />
                  <br className="big-br" />
                  <TextField
                    underlineFocusStyle={{color:"#979CF2"}}
                    floatingLabelFocusStyle={{color:"#979CF2"}}
                    multiLine={true}
                    rows={1}
                    rowsMax={2}
                    fullWidth={true}
                    onChange={this.updateDiscoveryDescription}
                    value={this.state.discoveryDescription}
                    floatingLabelText="Enter a short description of your discovery"
                    floatingLabelFixed={true}
                    />
                  </Dialog>
                  <Dialog
                    actions={loginPrompt_actions}
                    modal={false}
                    open={this.state.promptLoginOpen}
                    onRequestClose={this.promptGoggleLoginClose}
                    contentStyle={{width:"380px", textAlign:"center"}}
                    actionsContainerStyle={{textAlign:"center"}}
                  >
                    Please log in with Google to save your discovery.
                  </Dialog>
                </div>


                <ExploreFilters
                  className="explore-filter"
                  updateFilterParams={this.updateFilterParams}
                  activeSummaryData={this.state.activeSummaryData}
                  fullSummaryData={this.state.fullSummaryData}
                  open={this.state.filtersOpen}
                  toggleFilters={this.toggleFilters}
                />

              <Paper className="explore-headline card left overview-size">
                  <div className="profile-container">
                    <span className="overview-title">Number of Datasets</span>
                    <br/>
                    <svg width="100%" height="10">
                      <line x1="0" y1="5" x2="100%" y2="5" stroke="gray"  />
                    </svg>
                    <br/>
                    <span className="overview-content">currently showing <br className="big-br" /><span className="active">{this.state.activeSummaryData.total_datasets} datasets</span> <br className="big-br" /> out of {this.state.fullSummaryData.total_datasets} total datasets</span>
                  </div>
                </Paper>
                <Paper className="explore-headline card left overview-size">
                  <div className="profile-container">
                    <span className="overview-title">Estimated Total Download Size</span>
                    <br/>
                    <svg width="100%" height="10">
                      <line x1="0" y1="5" x2="100%" y2="5" stroke="gray"  />
                    </svg>
                    <br/>
                    <span className="overview-content-download"> {getReadableFileSizeString(this.state.activeSummaryData.total_download_size)} </span>
                  </div>
                </Paper>
                <Paper className="explore-headline card left overview-size">
                  <div className="profile-container">
                    <span className="overview-title">User</span>
                    <br/>
                    <svg width="100%" height="10">
                      <line x1="0" y1="5" x2="100%" y2="5" stroke="gray" />
                    </svg>
                    <br/>
                    <div className="overview-content-user">
                      {this.state.firebase.uid ?
                      <div className="overview-content-user-active">
                        <div className="user-photo">
                          <img src={this.state.firebase.photo} alt="" width="75px" height="75px"/>
                        </div>
                        <div className="user-active-message">
                          <span>{"Hi, " + this.state.firebase.name + ". Thanks for using MetaSeek!"}</span>
                        </div>
                      </div>
                      : <span className="overview-content-user-inactive">Create an account or log in with Google to save your discoveries.</span>
                      }
                      <br className="big-br"/>
                      <RaisedButton
                        className="profile-button"
                        onClick={this.state.firebase.uid ?  this.triggerLogout : this.triggerGoogleLogin }
                        primary={this.state.firebase.uid ? false : true}
                        label={this.state.firebase.uid ? "Log Out" : "Log In With Google" }
                      />
                    </div>
                  </div>
                </Paper>

                <VizDashboard activeSummaryData={this.state.activeSummaryData} processing={this.state.processing}/>

                <Paper className="explore-table card three">
                  <ExploreTable getNextDataPage={this.getNextDataPage} getPreviousDataPage={this.getPreviousDataPage} dataTable={this.state.dataTable}/>
                </Paper>
              </div>
            </div>
          </MuiThemeProvider>
      </div>
    )
  }
});

export default Explore;
